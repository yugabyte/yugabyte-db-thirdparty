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
from build_definitions import *  # noqa
from yugabyte_db_thirdparty.builder import Builder
from yugabyte_db_thirdparty.custom_logging import (
    log_separator,
    heading,
    configure_logging,
)
from yugabyte_db_thirdparty.multi_build import MultiBuilder
from yugabyte_db_thirdparty.remote_build import build_remotely
from yugabyte_db_thirdparty.shared_library_checking import get_lib_tester
from yugabyte_db_thirdparty.download_manager import DownloadManager
import json
import yaml

import_submodules(build_definitions)


def main() -> None:
    configure_logging()

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

    if builder.args.multi_build:
        multi_builder = MultiBuilder(conf_name_pattern=builder.args.multi_build_conf_name_pattern)
        multi_builder.build()
        return

    builder.finish_initialization()
    builder.run()
    if builder.args.license_report:
        with open('license_report.json', 'w') as output_file:
            json.dump(builder.license_report, output_file, indent=2)

        with open('fossa_modules.yml', 'w') as output_file:
            yaml.dump(builder.fossa_modules, output_file, indent=2)

    if not builder.args.download_extract_only:
        # Check that the executables and libraries we have built don't depend on any unexpected
        # dynamic libraries installed on this system.
        lib_tester = get_lib_tester()
        lib_tester.add_allowed_shared_lib_paths(builder.additional_allowed_shared_lib_paths)
        lib_tester.run()


if __name__ == "__main__":
    main()
