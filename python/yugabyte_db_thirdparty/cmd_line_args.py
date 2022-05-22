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
import platform

from typing import Dict, Set

from sys_detection import is_macos, local_sys_conf

from yugabyte_db_thirdparty.checksums import CHECKSUM_FILE_NAME
from yugabyte_db_thirdparty.util import log
from yugabyte_db_thirdparty.toolchain import TOOLCHAIN_TYPES
from yugabyte_db_thirdparty.constants import ADD_CHECKSUM_ARG
from build_definitions import BUILD_TYPES


INCOMPATIBLE_ARGUMENTS: Dict[str, Set[str]] = {
    'toolchain': {'devtoolset', 'compiler_prefix', 'compiler_suffix'},
    'check_libs_only': {'download_extract_only', 'create_package'},
}


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
                        action='store_true',
                        default=False,
                        help='Clean, but keep downloads.')
    parser.add_argument('--clean-downloads',
                        action='store_true',
                        default=False,
                        help='Clean, including downloads.')
    parser.add_argument(ADD_CHECKSUM_ARG,
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
        '--license-report',
        action='store_true',
        help='Generate a license report.')

    parser.add_argument(
        '--toolchain',
        help='Automatically download, install and use the given toolchain',
        choices=TOOLCHAIN_TYPES)

    parser.add_argument(
        '--create-package',
        help='Create the package tarball',
        action='store_true')

    parser.add_argument(
        '--upload-as-tag',
        help='Upload the package tarball as a GitHub release under this tag. '
             'Implies --create-package. Requires GITHUB_TOKEN to be set. If GITHUB_TOKEN is not '
             'set, this is a no-op (with success exit code).')

    parser.add_argument(
        '--expected-major-compiler-version',
        type=int,
        help='Expect the major version of the compiler to be as specified')

    parser.add_argument(
        '--verbose',
        help='Show verbose output',
        action='store_true')

    parser.add_argument(
        'dependencies',
        nargs=argparse.REMAINDER,
        help='Dependencies to build.')

    parser.add_argument(
        '--enforce_arch',
        help='Ensure that we use the given architecture, such as arm64. Useful for macOS systems '
             'with Apple Silicon CPUs and Rosetta 2 installed that can switch between '
             'architectures.')

    parser.add_argument(
        '--force',
        help='Build dependencies even though the system does not detect any changes compared '
             'to an earlier completed build.',
        action='store_true')

    parser.add_argument(
        '--delete-build-dir', '--remove-build-dir',
        help="Delete each dependency's build directory to start each build from scratch. "
             "Note that this does not affect the corresponding source directory.",
        action='store_true')

    parser.add_argument(
        '--lto',
        help='Link time optimization (LTO) type. The "full" and "thin" LTO types are the '
             'according to the LLVM terminology (see '
             'https://llvm.org/docs/LinkTimeOptimization.html).',
        choices=['full', 'thin'],
        default=None
    )

    parser.add_argument(
        '--check-libs-only',
        action='store_true',
        help='Do not build anything. Only check the dependencies of installed executables and '
             'libraries.'
    )

    args = parser.parse_args()

    # ---------------------------------------------------------------------------------------------
    # Validating arguments
    # ---------------------------------------------------------------------------------------------

    if args.dependencies and args.skip:
        raise ValueError("--skip is not compatible with specifying a list of dependencies to build")

    if is_macos():
        if args.single_compiler_type not in [None, 'clang']:
            raise ValueError(
                "--single-compiler-type=%s is not allowed on macOS" % args.single_compiler_type)
        args.single_compiler_type = 'clang'

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

    is_remote_build = args.remote_build_server is not None

    if args.devtoolset is not None and not is_remote_build:
        if not local_sys_conf().is_redhat_family():
            raise ValueError("--devtoolset can only be used on Red Hat Enterprise Linux OS family")
        if args.single_compiler_type not in [None, 'gcc']:
            raise ValueError(
                "--devtoolset is not compatible with compiler type: %s" % args.single_compiler_type)
        args.single_compiler_type = 'gcc'

    if args.enforce_arch and platform.machine() != args.enforce_arch:
        raise ValueError("Machine architecture is %s but we expect %s" % (
            platform.machine(), args.enforce_arch))

    if args.verbose:
        # This is used e.g. in compiler_wrapper.py.
        os.environ['YB_THIRDPARTY_VERBOSE'] = '1'

    incompatible_args = False
    for arg1_name, incompatible_arg_set in INCOMPATIBLE_ARGUMENTS.items():
        if getattr(args, arg1_name):
            for arg2_name in incompatible_arg_set:
                if getattr(args, arg2_name):
                    log("Incompatible arguments: %s and %s",
                        "--" + arg1_name.replace('_', '-'),
                        "--" + arg2_name.replace('_', '-'))
                    incompatible_args = True
    if incompatible_args:
        raise ValueError("Some incompatible arguments were specified. "
                         "See the messages above for details.")
    return args
