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

import build_definitions
import time

from build_definitions import *  # noqa
from yugabyte_db_thirdparty.arch import verify_arch
from yugabyte_db_thirdparty.builder import Builder
from yugabyte_db_thirdparty.custom_logging import (
    log_separator,
    heading,
    configure_logging,
)
from yugabyte_db_thirdparty.packager import Packager
from yugabyte_db_thirdparty.remote_build import build_remotely
from yugabyte_db_thirdparty.library_checking import get_lib_tester
from yugabyte_db_thirdparty.clang_util import get_clang_library_dir

import_submodules(build_definitions)


def main() -> None:
    configure_logging()
    verify_arch()

    unset_env_var_if_set('CC')
    unset_env_var_if_set('CXX')

    if 'YB_BUILD_THIRDPARTY_DUMP_ENV' in os.environ:
        heading('Environment of {}:'.format(sys.argv[0]))
        for key in os.environ:
            log('{}={}'.format(key, os.environ[key]))
        log_separator()

    builder = Builder()
    builder.parse_args()
    if builder.remote_build:
        build_remotely(
            remote_server=builder.args.remote_build_server,
            remote_build_code_path=builder.args.remote_build_dir)
        return

    builder.finish_initialization()

    start_time_sec = time.time()
    if builder.args.check_libs_only:
        log("Skipping build, --check-libs-only is specified")
    else:
        builder.run()
        log("Build finished in %.1f sec", time.time() - start_time_sec)

    if not builder.args.download_extract_only:
        lib_checking_start_time_sec = time.time()

        lib_tester = get_lib_tester()
        lib_tester.add_allowed_shared_lib_paths(builder.additional_allowed_shared_lib_paths)
        if builder.compiler_choice.is_linux_clang():
            lib_tester.add_allowed_shared_lib_paths({
                get_clang_library_dir(builder.compiler_choice.get_c_compiler())
            })
        lib_tester.configure_for_compiler_type(builder.compiler_choice.compiler_type)

        lib_tester.run()

        log("Libraries checked in %.1f sec", time.time() - lib_checking_start_time_sec)

    if builder.args.create_package or builder.args.upload_as_tag:
        packaging_and_upload_start_time_sec = time.time()

        packager = Packager()
        packager.create_package()

        if builder.args.upload_as_tag:
            github_token = os.environ.get('GITHUB_TOKEN')
            if github_token is not None and github_token.strip():
                packager.upload_package(builder.args.upload_as_tag)
            else:
                log("GITHUB_TOKEN is not set, not uploading the release package")

        log("Time taken for packaging/upload %.1f sec",
            time.time() - packaging_and_upload_start_time_sec)


if __name__ == "__main__":
    main()
