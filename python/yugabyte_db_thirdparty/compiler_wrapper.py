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

        use_ccache = os.getenv('YB_THIRDPARTY_USE_CCACHE') == 1

        compiler_args = sys.argv[1:]
        compiler_path_and_args = [real_compiler_path] + compiler_args

        if use_ccache:
            os.environ['CCACHE_COMPILER'] = real_compiler_path
            cmd_args = ['ccache', 'compiler'] + compiler_args
        else:
            cmd_args = compiler_path_and_args
        subprocess.check_call(cmd_args)


def run_compiler_wrapper(is_cxx: bool) -> None:
    compiler_wrapper = CompilerWrapper(is_cxx=is_cxx)
    compiler_wrapper.run()


if __name__ == '__main__':
    pass
