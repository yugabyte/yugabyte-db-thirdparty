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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class RapidJsonDependency(Dependency):
    def __init__(self) -> None:
        super(RapidJsonDependency, self).__init__(
            name='rapidjson',
            version='1.1.0-yb-2',
            url_pattern='https://github.com/yugabyte/rapidjson/archive/v{0}.zip',
            build_group=BuildGroup.COMMON)
        self.copy_sources = False

    def build(self, builder: BuilderInterface) -> None:
        builder.copy_include_files(
            dep=self,
            rel_src_include_path='include/rapidjson',
            dest_include_path='rapidjson')
