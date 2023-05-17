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


class HdrHistogramDependency(Dependency):
    def __init__(self) -> None:
        super(HdrHistogramDependency, self).__init__(
            'hdrhistogram',
            '0.11.6-yb-3',
            'https://github.com/yugabyte/HdrHistogram_c/archive/hdrhistogram-{0}.tar.gz',
            BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True

    def get_additional_cmake_args(self, builder: BuilderInterface) -> List[str]:
        return [
            '-DCMAKE_BUILD_TYPE=Release',
            '-DHDR_HISTOGRAM_BUILD_PROGRAMS=OFF',
            '-DHDR_LOG_REQUIRED=DISABLED',
        ]

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(dep=self, shared_and_static=True)
