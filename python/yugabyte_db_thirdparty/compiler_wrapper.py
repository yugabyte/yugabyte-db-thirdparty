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
    COMPILER_WRAPPER_ENV_VAR_NAME_TRACK_INCLUDES_IN_SUBDIRS_OF,
    COMPILER_WRAPPER_ENV_VAR_NAME_SAVE_USED_INCLUDE_TAGS_IN_DIR,
)

from yugabyte_db_thirdparty import file_util
from yugabyte_db_thirdparty.env_helpers import get_env_var_name_and_value_str, get_bool_env_var
from yugabyte_db_thirdparty import compile_commands, constants, compiler_flag_util


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

    track_includes_in_subdirs_of: Optional[str]
    save_used_include_tags_in_dir: Optional[str]

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

        self.track_includes_in_subdirs_of = os.getenv(
            COMPILER_WRAPPER_ENV_VAR_NAME_TRACK_INCLUDES_IN_SUBDIRS_OF)

        # For each include file under the "tracked" directory (above), we will create a
        # corresponding "tag file" in a directory tree rooted under this directory. We will use
        # those tag files to copy the needed include files into the thirdparty installed directory
        # as well as into our pre-packaged Intel oneAPI archive.
        self.save_used_include_tags_in_dir = os.getenv(
            COMPILER_WRAPPER_ENV_VAR_NAME_SAVE_USED_INCLUDE_TAGS_IN_DIR)

        if ((self.track_includes_in_subdirs_of is None) !=
                (self.save_used_include_tags_in_dir is None)):
            raise ValueError(
                'Expected the following two environment variables to be set or unset at the same '
                'time: ' +
                ', '.join([
                    get_env_var_name_and_value_str(
                        COMPILER_WRAPPER_ENV_VAR_NAME_TRACK_INCLUDES_IN_SUBDIRS_OF),
                    get_env_var_name_and_value_str(
                        COMPILER_WRAPPER_ENV_VAR_NAME_SAVE_USED_INCLUDE_TAGS_IN_DIR),
                ]))

        if self.track_includes_in_subdirs_of:
            assert self.save_used_include_tags_in_dir is not None  # Needed by MyPy.

            for env_var_name, env_var_value in (
                    (COMPILER_WRAPPER_ENV_VAR_NAME_TRACK_INCLUDES_IN_SUBDIRS_OF,
                     self.track_includes_in_subdirs_of),
                    (COMPILER_WRAPPER_ENV_VAR_NAME_SAVE_USED_INCLUDE_TAGS_IN_DIR,
                     self.save_used_include_tags_in_dir)):

                assert os.path.isabs(env_var_value), \
                    "Expected an absolute path for the value of the environment variable " + \
                    env_var_name + ", got: " + env_var_value

                assert os.path.isdir(env_var_value), \
                    "Directory specified by the " + env_var_name + " environment variable " + \
                    "does not exist: " + self.save_used_include_tags_in_dir

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

    def check_cxx_standard_version_flags(self, cmd_args: List[str]) -> None:
        cxx_standard_version_set: Set[str] = compiler_flag_util.get_cxx_standard_version_set(
            cmd_args)
        if not any(compiler_flag_util.is_correct_cxx_standard_version(v)
                   for v in cxx_standard_version_set):
            raise ValueError(
                f"The correct C++ standard {constants.CXX_STANDARD} is not among the "
                f"specified flags: {cxx_standard_version_set}. "
                f"Command line: {shlex_join(cmd_args)}.")
        if len(cxx_standard_version_set) > 1:
            error_msg = \
                f"Contradictory C++ standards specified: {sorted(cxx_standard_version_set)}, " \
                f"replacing with {constants.CXX_STANDARD} only"
            cmd_args[:] = compiler_flag_util.remove_incorrect_cxx_standard_flags(cmd_args)
            # We have made sure that the correct C++ standard is included in the arguments.

    def run_preprocessor(
            self,
            output_path: str) -> None:
        """
        Run the preprocessor and parse preprocessor output. As part of this output, we see all
        absolute header paths actually used. This allows us to:
        - Collect the headers from a certain library, such as Intel oneAPI, so that we can copy only
          the required subset of those headers to our installation directory. The entire oneAPI
          installation could be over 14 GB, which is prohibitive for Docker images and third-party
          archives.

          E.g. the following command can be used to sum up all header file sizes in the Intel oneAPI
          installation, and it results in ~72 MiB as of 2024. The parentheses and semicolon have to
          be escaped with backslashes if you decide to run it.

          find /opt/intel/oneapi ( -name "*.h" -or -name "*.hpp" ) -type f -exec ls -l {} ; |
            awk '{S += $5} END {print S}

        - Disallow using headers from certain directories, e.g. system directories when building
          with Linuxbrew glibc.

        :param output_path: the output path of the compilation command
        """
        pp_output_path = output_path + '.pp'  # "pp" for "preprocessed"

        # Perform preprocessing to ensure we are only using include files from allowed directories.
        pp_args = [self.real_compiler_path] + with_updated_output_path(
            self.compiler_args, pp_output_path)

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

        if self.track_includes_in_subdirs_of is not None:
            include_file_abs_path_prefix = self.track_includes_in_subdirs_of + '/'
            for include_file_path in real_included_files:
                if include_file_path.startswith(include_file_abs_path_prefix):
                    include_file_rel_path = include_file_path[len(include_file_abs_path_prefix):]

                    assert self.save_used_include_tags_in_dir is not None

                    tag_file_dir = file_util.create_intermediate_dirs_for_rel_path(
                        self.save_used_include_tags_in_dir, include_file_rel_path)

                    tag_file_path = os.path.join(
                        tag_file_dir, os.path.basename(include_file_rel_path))
                    if os.path.islink(include_file_path):
                        symlink_target = os.readlink(include_file_path)
                        assert not os.path.isabs(symlink_target), \
                            f"Did not expect include file {include_file_path} to be a symbolic " \
                            f"link to an absolute path: {symlink_target}"
                        # The "tag file" will be symlink pointing to the same relative path.
                        os.symlink(symlink_target, tag_file_path)
                    else:
                        # Write an empty file.
                        with open(tag_file_path, 'w') as tag_file:
                            pass

    def handle_compilation_command(self, output_files: List[str]) -> None:
        if (len(output_files) != 1 or
                not output_files[0].endswith('.o') or
                # Protobuf build produces a file named libprotobuf.15.dylib-master.o out of multiple
                # .o files.
                output_files[0].endswith('.dylib-master.o')):
            return

        output_path = output_files[0]
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

        if not is_assembly_input:
            self.run_preprocessor(output_path)

        if generate_compile_command_file:
            assert compile_commands_tmp_dir is not None
            compile_command_path = compile_commands.get_compile_command_path_for_output_file(
                compile_commands_tmp_dir, output_path)
            file_util.mkdir_p(os.path.dirname(compile_command_path))
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

    def run(self) -> None:
        verbose = get_bool_env_var('YB_THIRDPARTY_VERBOSE')
        use_ccache = get_bool_env_var('YB_THIRDPARTY_USE_CCACHE')

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

        if self.is_cxx and not is_linking and not get_bool_env_var('YB_THIRDPARTY_CONFIGURING'):
            self.check_cxx_standard_version_flags(cmd_args)

        if is_linking:
            cmd_args.extend(
                os.environ.get(
                    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_APPEND, '').strip().split())

            ld_flags_to_remove: Set[str] = set(os.environ.get(
                    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_REMOVE, '').strip().split())
            cmd_args = [arg for arg in cmd_args if arg not in ld_flags_to_remove]

        self.handle_compilation_command(output_files)

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
