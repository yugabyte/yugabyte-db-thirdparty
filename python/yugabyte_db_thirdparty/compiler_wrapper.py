#!/usr/bin/env python3

import sys
import os
import subprocess
import logging
import json
import shlex

from typing import List, Dict

from yugabyte_db_thirdparty.util import shlex_join


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

        use_ccache = os.getenv('YB_THIRDPARTY_USE_CCACHE') == '1'

        compiler_args = sys.argv[1:]
        compiler_path_and_args = [real_compiler_path] + compiler_args

        if use_ccache:
            os.environ['CCACHE_COMPILER'] = real_compiler_path
            cmd_args = ['ccache', 'compiler'] + compiler_args
        else:
            cmd_args = compiler_path_and_args

        output_files = []
        for i in range(len(compiler_args) - 1):
            if compiler_args[i] == '-o':
                output_files.append(compiler_args[i + 1])

        if len(output_files) == 1 and output_files[0].endswith('.o'):
            pp_output_path = None
            # Perform preprocessing only to ensure we are using the correct include directories.
            pp_args = [real_compiler_path]
            out_file_arg_follows = False
            assembly_input = False
            for arg in compiler_args:
                if arg.endswith('.s'):
                    assembly_input = True
                if out_file_arg_follows:
                    assert pp_output_path is None
                    pp_output_path = arg + '.pp'
                    pp_args.append(pp_output_path)
                else:
                    pp_args.append(arg)
                out_file_arg_follows = arg == '-o'
            if not assembly_input:
                pp_args.append('-E')
                sys.stderr.write("Preprocessor args: %s" % shlex_join(pp_args))
                subprocess.check_call(pp_args)
                assert pp_output_path is not None
                assert os.path.isfile(pp_output_path)

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
                sys.stderr.write("Included files:\n%s" % "\n".join(sorted(real_included_files)))

        subprocess.check_call(cmd_args)
        cmd_str = '( cd %s; %s )' % (shlex.quote(os.getcwd()), shlex_join(cmd_args))
        sys.stderr.write(cmd_str)


def run_compiler_wrapper(is_cxx: bool) -> None:
    compiler_wrapper = CompilerWrapper(is_cxx=is_cxx)
    compiler_wrapper.run()


if __name__ == '__main__':
    pass
