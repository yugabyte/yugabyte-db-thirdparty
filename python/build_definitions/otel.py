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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class OtelDependency(Dependency):
    def __init__(self) -> None:
        super(OtelDependency, self).__init__(
            name='opentelemetry-cpp',
            version='1.8.2.v1',
            url_pattern='https://github.com/vrajat/opentelemetry-cpp/archive/refs/tags/v{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = False

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(self,
                                 ['-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
                                  '-DBUILD_SHARED_LIBS=ON',
                                  '-DWITH_OTLP=ON',
                                  '-DWITH_BENCHMARK=OFF',
                                  "-DOTELCPP_PROTO_PATH={path}".format(path=os.path.join(builder.fs_layout.tp_src_dir, "opentelemetry-proto-0.1.2"))])