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

from typing import List, Set

from yugabyte_db_thirdparty.util import shlex_join, is_shared_library_name
from yugabyte_db_thirdparty.constants import (
    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_APPEND,
    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_REMOVE,
)


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
        self.compiler_args = self.filter_args(sys.argv[1:])

    def get_copy_paste_friendly_cmd_str(self, cmd_args: List[str] = []) -> str:
        if not cmd_args:
            cmd_args = self.get_compiler_path_and_args()
        return '( cd %s; %s )' % (shlex.quote(os.getcwd()), shlex_join(cmd_args))

    def log(self, err_msg: str) -> None:
        sys.stderr.write(err_msg + '\n')

    def is_permitted_arg(self, arg: str) -> bool:
        if not arg.startswith('-I'):
            return True
        include_path = arg[1:]
        if include_path.startswith('"') and include_path.endswith('"') and len(include_path) >= 2:
            include_path = include_path[1:-1]
        return include_path not in self.disallowed_include_dirs

    def filter_args(self, compiler_args: List[str]) -> List[str]:
        return [arg for arg in compiler_args if self.is_permitted_arg(arg)]

    def get_compiler_path_and_args(self) -> List[str]:
        return [self.real_compiler_path] + self.compiler_args

    def get_compiler_command_str(self) -> str:
        return shlex_join(self.get_compiler_path_and_args())

    def check_actual_included_files(self) -> None:
        """
        Modify the compiler command line to only run the preprocessor. Look at files that got
        included and verify that no files from disallowed directories are present.
        """
        pp_output_path = None
        pp_args = [self.real_compiler_path]
        out_file_arg_follows = False
        assembly_input = False
        for arg in self.compiler_args:
            if arg.endswith('.s'):
                assembly_input = True
            if out_file_arg_follows:
                assert pp_output_path is None
                pp_output_path = arg + '.pp'
                pp_args.append(pp_output_path)
            else:
                pp_args.append(arg)
            out_file_arg_follows = arg == '-o'
        if assembly_input:
            return
        pp_args.append('-E')
        subprocess.check_call(pp_args)
        assert pp_output_path is not None
        assert os.path.isfile(pp_output_path)

        # Collect included files from preprocessor output.
        # https://gcc.gnu.org/onlinedocs/cpp/Preprocessor-Output.html
        included_files: Set[str] = set()
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
                            self.get_compiler_command_str()))

    def check_duplicate_isystem_paths(self) -> None:
        """
        Checks if any directories specified with -isystem are duplicated. This is not allowed
        because it can cause subtle errors due to usage of include_next in some standard headers.
        E.g. the compilation error can say that some standard C library headers are not found.
        """

        prev_is_isystem = False
        isystem_paths: Set[str] = set()
        duplicate_isystem_paths: Set[str] = set()
        for arg in self.compiler_args:
            if prev_is_isystem:
                if arg in isystem_paths:
                    duplicate_isystem_paths.add(arg)
                else:
                    isystem_paths.add(arg)
            prev_is_isystem = arg == '-isystem'
        if duplicate_isystem_paths:
            filtered_isystem_paths = [
                p for p in duplicate_isystem_paths
                # These paths get duplicated on the command line but interestingly it does not cause
                # the build to fail.
                if not p.endswith('/installed/common/include')
            ]
            if filtered_isystem_paths:
                err_msg = 'Disallowed duplicate isystem paths: %s. Command: %s' % (
                    ', '.join(sorted(filtered_isystem_paths)),
                    self.get_copy_paste_friendly_cmd_str())
                self.log(err_msg)
                raise ValueError(err_msg)

    def run(self) -> None:
        verbose: bool = os.environ.get('YB_THIRDPARTY_VERBOSE') == '1'

        use_ccache = os.getenv('YB_THIRDPARTY_USE_CCACHE') == '1'

        cmd_args: List[str]
        if use_ccache:
            os.environ['CCACHE_COMPILER'] = self.real_compiler_path
            cmd_args = ['ccache', 'compiler'] + self.compiler_args
        else:
            cmd_args = self.get_compiler_path_and_args()

        self.check_duplicate_isystem_paths()

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

        if len(output_files) == 1 and output_files[0].endswith('.o'):
            self.check_actual_included_files()

        cmd_str = self.get_copy_paste_friendly_cmd_str(cmd_args)

        if verbose:
            self.log("Running command: %s" % cmd_str)

        try:
            subprocess.check_call(cmd_args)
        except subprocess.CalledProcessError as ex:
            sys.stderr.write("Command failed with exit code %d: %s\n" % (ex.returncode, cmd_str))
            raise ex


def run_compiler_wrapper(is_cxx: bool) -> None:
    compiler_wrapper = CompilerWrapper(is_cxx=is_cxx)
    compiler_wrapper.run()


if __name__ == '__main__':
    pass
