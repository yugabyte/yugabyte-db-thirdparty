#!/usr/bin/env python3

import sys
import os
import subprocess
import logging
import json

from typing import List, Dict


class CompilerWrapper:
    is_cxx: bool
    args: List[str]

    def __init__(self, is_cxx: bool) -> None:
        self.is_cxx = is_cxx
        self.args = sys.argv

    def run(self) -> None:
        if self.is_cxx:
            real_compiler_path = os.environ['YB_THIRDPARTY_REAL_CXX_COMPILER']
            language = 'C++'
        else:
            real_compiler_path = os.environ['YB_THIRDPARTY_REAL_C_COMPILER']
            language = 'C'

        os.environ['CCACHE_COMPILER'] = real_compiler_path
        compiler_args = sys.argv[1:]
        compiler_path_and_args = [real_compiler_path] + compiler_args
        subprocess.check_call(['ccache', 'compiler'] + compiler_args)

        self.check_compiler_output(compiler_args)

    def check_compiler_output(self, compiler_args: List[str]) -> None:
        # Watch for libstdc++ in linker output and error out immediately.
        disallow_libstdcxx = os.environ['YB_THIRDPARTY_DISALLOW_LIBSTDCXX']
        if not disallow_libstdcxx:
            return

        output_file = None
        for i in range(len(compiler_args) - 1):
            if compiler_args[i] == '-o':
                output_file = compiler_args[i]

        if output_file.endswith('.so'):
            from yugabyte_db_thirdparty.shared_library_checking import LibTestLinux
            lib_tester = LibTestLinux()
            lib_tester.bad_lib_re_list.append('.*libstdc.*')
            lib_tester.init_regex()
            if not lib_tester.good_libs(output_file):
                raise ValueError(
                    "Library or executable depeends on disallowed libraries: %s" %
                        os.path.abspath(output_file))


def run_compiler_wrapper(is_cxx: bool) -> None:
    compiler_wrapper = CompilerWrapper(is_cxx=is_cxx)
    compiler_wrapper.run()


if __name__ == '__main__':
    pass
