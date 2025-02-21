#
# Copyright (c) YugaByte, Inc.
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

import os
import sys
from build_definitions import ExtraDownload

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class ProtobufDependency(Dependency):
    def __init__(self) -> None:
        super(ProtobufDependency, self).__init__(
            'protobuf',
            '21.12-yb-1',
            'https://github.com/yugabyte/protobuf/archive/refs/tags/v{0}.tar.gz',
            BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True
        self.extra_downloads = [
            ExtraDownload(
                name='gmock',
                version='1.7.0',
                url_pattern='https://github.com/google/googlemock/archive/release-{0}.zip',
                dir_name='gmock'
            ),
            ExtraDownload(
                name='gtest',
                version='1.7.0',
                url_pattern='https://github.com/google/googletest/archive/release-{0}.zip',
                dir_name='gmock/gtest'
            )
        ]

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(
            dep=self,
            extra_configure_args=[
                '--with-pic', '--enable-shared', '--enable-static', '--without-js'
            ],
            run_autogen=True
        )

    def use_cppflags_env_var(self) -> bool:
        return True
