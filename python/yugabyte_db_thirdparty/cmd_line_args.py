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
#

import argparse
import sys
import os

from yugabyte_db_thirdparty.checksums import CHECKSUM_FILE_NAME
from yugabyte_db_thirdparty.os_detection import is_centos, is_mac
from yugabyte_db_thirdparty.util import log
from build_definitions import BUILD_TYPES


def parse_cmd_line_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=sys.argv[0])
    parser.add_argument('--build-type',
                        default=None,
                        type=str,
                        choices=BUILD_TYPES,
                        help='Build only specific part of thirdparty dependencies.')
    parser.add_argument('--skip-sanitizers',
                        action='store_true',
                        help='Do not build ASAN and TSAN instrumented dependencies.')
    parser.add_argument('--clean',
                        action='store_const',
                        const=True,
                        default=False,
                        help='Clean.')
    parser.add_argument('--add_checksum',
                        help='Compute and add unknown checksums to %s' % CHECKSUM_FILE_NAME,
                        action='store_true')
    parser.add_argument('--skip',
                        help='Dependencies to skip')

    parser.add_argument(
        '--single-compiler-type',
        type=str,
        choices=['gcc', 'clang'],
        default=None,
        help='Produce a third-party dependencies build using only a single compiler. '
             'This also implies that we are not using Linuxbrew.')

    parser.add_argument(
        '--compiler-prefix',
        type=str,
        help='The prefix directory for looking for compiler executables. We will look for '
             'compiler executable in the bin subdirectory of this directory.')

    parser.add_argument(
        '--compiler-suffix',
        type=str,
        default='',
        help='Suffix to append to compiler executables, such as the version number, '
             'potentially prefixed with a dash, to obtain names such as gcc-8, g++-8, '
             'clang-10, or clang++-10.')

    parser.add_argument(
        '--devtoolset',
        type=int,
        help='Specifies a CentOS devtoolset')

    parser.add_argument(
        '-j', '--make-parallelism',
        help='How many cores should the build use. This is passed to '
              'Make/Ninja child processes. This can also be specified using the '
              'YB_MAKE_PARALLELISM environment variable.',
              type=int)

    parser.add_argument(
        '--use-ccache',
        action='store_true',
        help='Use ccache to speed up compilation')

    parser.add_argument(
        '--use-compiler-wrapper',
        action='store_true',
        help='Use a compiler wrapper script. Allows additional validation but '
             'makes the build slower.')

    parser.add_argument(
        '--llvm-version',
        default=None,
        help='Version (tag) to use for dependencies based on LLVM codebase')

    parser.add_argument(
        '--remote-build-server',
        help='Build third-party dependencies remotely on this server. The default value is '
             'determined by YB_THIRDPARTY_REMOTE_BUILD_SERVER environment variable.',
        default=os.getenv('YB_THIRDPARTY_REMOTE_BUILD_SERVER'))

    parser.add_argument(
        '--remote-build-dir',
        help='The directory on the remote server to build third-party dependencies in. The '
             'value is determined by the YB_THIRDPARTY_REMOTE_BUILD_DIR environment variable.',
        default=os.getenv('YB_THIRDPARTY_REMOTE_BUILD_DIR'))

    parser.add_argument(
        '--local',
        help='Forces the local build even if --remote-... options are specified or the '
             'corresponding environment variables are set.',
        action='store_true')

    parser.add_argument(
        '--download-extract-only',
        help='Only download and extract archives. Do not build any dependencies.',
        action='store_true')

    parser.add_argument(
        'dependencies',
        nargs=argparse.REMAINDER,
        help='Dependencies to build.')

    subparsers = parser.add_subparsers(help='sub-command help', dest='command')
    multi_build_parser = subparsers.add_parser(
        'multi-build',
        help='Build multiple configurations in parallel')

    multi_build_parser.add_argument(
        '--conf-name-pattern',
        help='Only build configurations matching this glob-style pattern, anchored on both ends.')

    args = parser.parse_args()

    if args.dependencies and args.skip:
        raise ValueError("--skip is not compatible with specifying a list of dependencies to build")

    if is_mac():
        if args.single_compiler_type not in [None, 'clang']:
            raise ValueError(
                "--single-compiler-type=%s is not allowed on macOS" % args.single_compiler_type)
        args.single_compiler_type = 'clang'

    if args.devtoolset is not None:
        if not is_centos():
            raise ValueError("--devtoolset can only be used on CentOS Linux")
        if args.single_compiler_type not in [None, 'gcc']:
            raise ValueError(
                "--devtoolset is not compatible with compiler type: %s" % args.single_compiler_type)
        args.single_compiler_type = 'gcc'

    if args.llvm_version is None:
        if args.compiler_suffix == '-10':
            args.llvm_version = '10.0.1'
        elif args.compiler_suffix == '-11':
            args.llvm_version = '11.0.0'
        else:
            args.llvm_version = '11.0.0'
        log("Will use the version %s of LLVM libraries (libunwind, libc++)",
            args.llvm_version)

    if args.local and (args.remote_build_server is not None or args.remote_build_dir is not None):
        log("Forcing a local build")
        args.remote_build_server = None
        args.remote_build_dir = None

    if (args.remote_build_server is None) != (args.remote_build_dir is None):
        raise ValueError(
            '--remote-build-server and --remote-build-dir have to be specified or unspecified '
            'at the same time. Note that their default values are provided by corresponding '
            'environment variables, YB_THIRDPARTY_REMOTE_BUILD_SERVER and '
            'YB_THIRDPARTY_REMOTE_BUILD_DIR.')
    if args.remote_build_dir is not None:
        assert os.path.isabs(args.remote_build_dir), (
            'Remote build directory path must be an absolute path: %s' % args.remote_build_dir)

    return args
