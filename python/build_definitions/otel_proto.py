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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class OtelProtoDependency(Dependency):
    def __init__(self) -> None:
        super(OtelProtoDependency, self).__init__(
            name='opentelemetry-proto',
            version='0.19.0',
            url_pattern='https://github.com/open-telemetry/opentelemetry-proto/'
                        + 'archive/refs/tags/v{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.patches = ['otel_proto_remove_optional_keyword.patch']
        self.copy_sources = False

    def build(self, builder: BuilderInterface) -> None:
        pass
