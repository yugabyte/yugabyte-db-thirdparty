#!/usr/bin/env python3

# Copyright (c) Yugabyte, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
# in compliance with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied. See the License for the specific language governing permissions and limitations
# under the License.

import sys
import os
import shlex
import subprocess
import json

from copy import deepcopy

from typing import List, Set, Optional

from yugabyte_db_thirdparty.util import shlex_join, is_shared_library_name
from yugabyte_db_thirdparty.constants import (
    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_APPEND,
    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_REMOVE,
)
from yugabyte_db_thirdparty.util import mkdir_p
from yugabyte_db_thirdparty import compile_commands


C_CXX_SUFFIXES = ('.c', '.cc', '.cxx', '.cpp')


def cmd_join_one_arg_per_line(cmd_args: List[str]) -> str:
    return '\n'.join([
        '( \\',
        f'  cd {shlex.quote(os.getcwd())}; \\',
        f'  {shlex.quote(cmd_args[0])} \\',
        '    ' + ' \\\n    '.join(cmd_args[1:]) + ' \\',
        ')'
    ])


def with_updated_output_path(args: List[str], new_output_path: str) -> List[str]:
    """
    Updates the output path in the given compiler argument list and returns the new list.

    >>> with_updated_output_path(['g++', '-o', 'foo.o', 'foo.cc'], 'bar.o')
    ['g++', '-o', 'bar.o', 'foo.cc']
    """
    new_args = deepcopy(args)
    output_replaced = False
    for i in range(1, len(new_args)):
        if new_args[i - 1] == '-o':
            new_args[i] = new_output_path
            assert not output_replaced, (
                "Multiple output files specified: %s" % shlex_join(args))
            output_replaced = True
    return new_args


class CompilerWrapper:
    is_cxx: bool
    args: List[str]
    real_compiler_path: str
    language: str
    compiler_args: List[str]
    disallowed_include_dirs: List[str]

    def __init__(self, is_cxx: bool) -> None:
        self.is_cxx = is_cxx
        self.args = sys.argv
        if self.is_cxx:
            self.real_compiler_path = os.environ['YB_THIRDPARTY_REAL_CXX_COMPILER']
            self.language = 'C++'
        else:
            self.real_compiler_path = os.environ['YB_THIRDPARTY_REAL_C_COMPILER']
            self.language = 'C'

        disallowed_include_dirs_colon_separated = os.getenv('YB_DISALLOWED_INCLUDE_DIRS')
        self.disallowed_include_dirs = []
        if disallowed_include_dirs_colon_separated:
            self.disallowed_include_dirs = disallowed_include_dirs_colon_separated.split(':')
        self.compiler_args = self._filter_args(sys.argv[1:])

    def _is_permitted_arg(self, arg: str) -> bool:
        if not arg.startswith('-I'):
            return True
        include_path = arg[1:]
        if include_path.startswith('"') and include_path.endswith('"') and len(include_path) >= 2:
            include_path = include_path[1:-1]
        return include_path not in self.disallowed_include_dirs

    def _filter_args(self, compiler_args: List[str]) -> List[str]:
        return [arg for arg in compiler_args if self._is_permitted_arg(arg)]

    def _get_compiler_path_and_args(self) -> List[str]:
        return [self.real_compiler_path] + self.compiler_args

    def _get_compiler_command_str(self) -> str:
        return shlex_join(self._get_compiler_path_and_args())

    def run(self) -> None:
        verbose: bool = os.environ.get('YB_THIRDPARTY_VERBOSE') == '1'

        use_ccache = os.getenv('YB_THIRDPARTY_USE_CCACHE') == '1'

        cmd_args: List[str]
        if use_ccache:
            os.environ['CCACHE_COMPILER'] = self.real_compiler_path
            cmd_args = ['ccache', 'compiler'] + self.compiler_args
        else:
            cmd_args = self._get_compiler_path_and_args()

        output_files = []
        for i in range(len(self.compiler_args) - 1):
            if self.compiler_args[i] == '-o':
                output_files.append(self.compiler_args[i + 1])

        is_linking = [
            is_shared_library_name(output_file_name) for output_file_name in output_files
        ]

        if is_linking:
            cmd_args.extend(
                os.environ.get(
                    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_APPEND, '').strip().split())

            ld_flags_to_remove: Set[str] = set(os.environ.get(
                    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_REMOVE, '').strip().split())
            cmd_args = [arg for arg in cmd_args if arg not in ld_flags_to_remove]

        if (len(output_files) == 1 and
                output_files[0].endswith('.o') and
                # Protobuf build produces a file named libprotobuf.15.dylib-master.o out of multiple
                # .o files.
                not output_files[0].endswith('.dylib-master.o')):

            output_path = output_files[0]
            pp_output_path = output_path + '.pp'  # "pp" for "preprocessed"
            is_assembly_input = any([arg.endswith('.s') for arg in self.compiler_args])

            compile_commands_tmp_dir = compile_commands.get_tmp_dir_env_var()
            generate_compile_command_file = bool(compile_commands_tmp_dir) and not is_assembly_input

            input_file_candidates = []
            if generate_compile_command_file:
                input_file_candidates = [
                    arg for arg in self.compiler_args if (
                        arg.endswith(C_CXX_SUFFIXES) and
                        os.path.exists(arg)
                    )
                ]
                if len(input_file_candidates) != 1:
                    sys.stderr.write(
                        f"Could not determine input file name for compiler invocation, will omit "
                        f"from compile commands. Input file candidates: {input_file_candidates}, "
                        f"command line: {self._get_compiler_command_str()}"
                    )
                    generate_compile_command_file = False

            # Perform preprocessing to ensure we are only using include files from allowed
            # directories.
            pp_args = [self.real_compiler_path] + with_updated_output_path(
                self.compiler_args, pp_output_path)

            if not is_assembly_input:
                pp_args.append('-E')
                subprocess.check_call(pp_args)
                assert pp_output_path is not None
                assert os.path.isfile(pp_output_path), (
                    f"Preprocessed output file does not exist: {pp_output_path}. "
                    f"Preprocessing command arguments: {shlex_join(pp_args)}."
                )

                # Collect included files from preprocessor output.
                # https://gcc.gnu.org/onlinedocs/cpp/Preprocessor-Output.html
                included_files = set()
                with open(pp_output_path) as pp_output_file:
                    for line in pp_output_file:
                        if line.startswith('# 1 "'):
                            line = line[5:].rstrip()
                            if line.startswith('<'):
                                continue
                            quote_pos = line.find('"')
                            if quote_pos < 0:
                                continue
                            included_files.add(line[:quote_pos])
                real_included_files = set(os.path.realpath(p) for p in included_files)

                for disallowed_dir in self.disallowed_include_dirs:
                    for included_file in real_included_files:
                        if included_file.startswith(disallowed_dir + '/'):
                            raise ValueError(
                                "File from a disallowed directory included: %s. "
                                "Compiler invocation: %s" % (
                                    included_file,
                                    self._get_compiler_command_str()))

            if generate_compile_command_file:
                assert compile_commands_tmp_dir is not None
                compile_command_path = compile_commands.get_compile_command_path_for_output_file(
                    compile_commands_tmp_dir, output_path)
                mkdir_p(os.path.dirname(compile_command_path))
                assert len(input_file_candidates) == 1, \
                    "Expected exactly one input file candidate, got: %s" % input_file_candidates
                input_path = os.path.abspath(input_file_candidates[0])
                arguments = [self.real_compiler_path] + self.compiler_args

                with open(compile_command_path, 'w') as compile_command_file:
                    json.dump(dict(
                        directory=os.getcwd(),
                        file=input_path,
                        arguments=arguments
                    ), compile_command_file)

        cmd_str = '( cd %s; %s )' % (shlex.quote(os.getcwd()), shlex_join(cmd_args))

        if verbose:
            sys.stderr.write("Running command: %s" % cmd_str)

        try:
            subprocess.check_call(cmd_args)
        except subprocess.CalledProcessError as ex:
            sys.stderr.write(
                "Command failed with exit code %d (one argument per line): %s\n" % (
                    ex.returncode,
                    cmd_join_one_arg_per_line(cmd_args)))
            sys.stderr.write("Command failed with exit code %d: %s\n" % (ex.returncode, cmd_str))
            raise ex


def run_compiler_wrapper(is_cxx: bool) -> None:
    compiler_wrapper = CompilerWrapper(is_cxx=is_cxx)
    compiler_wrapper.run()


if __name__ == '__main__':
    pass
