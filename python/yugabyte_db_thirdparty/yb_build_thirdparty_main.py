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
#
#

import argparse
import build_definitions
import glob
import itertools
import time

from build_definitions import *  # noqa

from yugabyte_db_thirdparty.arch import verify_arch
from yugabyte_db_thirdparty.builder import Builder
from yugabyte_db_thirdparty.clang_util import get_clang_library_dir
from yugabyte_db_thirdparty.custom_logging import log_separator, heading, configure_logging
from yugabyte_db_thirdparty.library_checking import get_lib_tester
from yugabyte_db_thirdparty.packager import Packager
from yugabyte_db_thirdparty.remote_build import build_remotely
from yugabyte_db_thirdparty.snyk import run_snyk_scan
from yugabyte_db_thirdparty.util import log_and_run_cmd, YB_THIRDPARTY_DIR

from yugabyte_db_thirdparty import intel_oneapi, env_helpers


import_submodules(build_definitions)


# TODO: do we need to unset more than just these?
ENV_VARS_TO_AUTO_UNSET = ['CC', 'CXX']


class BuilderTool:
    builder: Builder
    args: argparse.Namespace

    def __init__(self) -> None:
        self.builder = Builder()

    def check_libraries(self) -> None:
        builder = self.builder
        lib_checking_start_time_sec = time.time()

        lib_tester = get_lib_tester(fs_layout=builder.fs_layout)
        lib_tester.add_allowed_shared_lib_paths(builder.additional_allowed_shared_lib_paths)
        if builder.compiler_choice.is_linux_clang():
            clang_library_dirs: List[str] = get_clang_library_dir(
                builder.compiler_choice.get_c_compiler(),
                all_dirs=True
            )
            assert len(clang_library_dirs) > 0
            lib_tester.add_allowed_shared_lib_paths(set(clang_library_dirs))
        lib_tester.configure_for_compiler(builder.compiler_choice)

        lib_tester.run()

        log("Libraries checked in %.1f sec", time.time() - lib_checking_start_time_sec)

    def create_and_upload_package(self) -> None:
        args = self.builder.args
        if args.cleanup_before_packaging:
            log("Cleaning up disk space before packaging")
            log_and_run_cmd(
                ['rm', '-rf'] + list(itertools.chain.from_iterable([
                    glob.glob(os.path.join(YB_THIRDPARTY_DIR, subdir_name, '*'))
                    for subdir_name in ['download', 'src', 'build']
                ])))

        packaging_and_upload_start_time_sec = time.time()

        packager = Packager()
        packager.create_package()

        if args.upload_as_tag:
            github_token = os.environ.get('GITHUB_TOKEN')
            if github_token is not None and github_token.strip():
                packager.upload_package(args.upload_as_tag)
            else:
                log("GITHUB_TOKEN is not set, not uploading the release package despite " +
                    "--upload-as-tag being specified")

        log("Time taken for packaging/upload %.1f sec",
            time.time() - packaging_and_upload_start_time_sec)

    def run(self) -> None:
        builder = self.builder
        builder.parse_args()

        args = self.builder.args
        if builder.remote_build:
            build_remotely(
                remote_server=args.remote_build_server,
                remote_build_code_path=args.remote_build_dir)
            return

        self.do_build()

    def do_build(self) -> None:
        builder = self.builder
        args = builder.args

        builder.finish_initialization()
        if args.package_intel_oneapi:
            intel_oneapi.enable_package_build_mode(
                installed_common_dir=builder.fs_layout.tp_installed_common_dir)
        if args.intel_oneapi_base_dir:
            intel_oneapi.find_intel_oneapi(base_dir=args.intel_oneapi_base_dir)

        start_time_sec = time.time()
        if args.check_libs_only:
            log("Skipping build, --check-libs-only is specified")
        else:
            builder.run()
            log("Build finished in %.1f sec", time.time() - start_time_sec)

        if args.package_intel_oneapi:
            intel_oneapi.find_intel_oneapi().create_package(dest_dir=os.getcwd())

        if not args.download_extract_only:
            self.check_libraries()

        if args.create_package or args.upload_as_tag:
            self.create_and_upload_package()

        if args.snyk:
            run_snyk_scan(builder.fs_layout)


def adjust_environment() -> None:
    for env_var_name in ENV_VARS_TO_AUTO_UNSET:
        env_helpers.unset_env_var_if_set_and_log(env_var_name)

    if 'YB_BUILD_THIRDPARTY_DUMP_ENV' in os.environ:
        env_helpers.dump_env_vars_to_log(sys.argv[0])


def main() -> None:
    configure_logging()
    verify_arch()
    adjust_environment()

    builder_tool = BuilderTool()
    builder_tool.run()


if __name__ == "__main__":
    main()
