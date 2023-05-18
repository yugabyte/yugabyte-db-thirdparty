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
    opentelemetry_proto_version = 'opentelemetry-proto-0.19.0'

    def __init__(self) -> None:
        super(OtelDependency, self).__init__(
            name='opentelemetry-cpp',
            version='1.9.0',
            url_pattern='https://github.com/open-telemetry/opentelemetry-cpp/'
                        + 'archive/refs/tags/v{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        # Patch fixes the following error with current protobuf installation
        # Missing value for flag: --experimental_allow_proto3_optional
        self.patches = ['otel_cpp_remove_experimental_allow_proto3_optional.patch',
                        'add_macOS_missing_dependencies.patch']
        self.copy_sources = False

    def build(self, builder: BuilderInterface) -> None:
        installed_common_dir = builder.fs_layout.tp_installed_common_dir
        src_dir = os.path.join(builder.fs_layout.tp_src_dir,
                               OtelDependency.opentelemetry_proto_version)
        builder.build_with_cmake(self,
                                 ['-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
                                  '-DCMAKE_BUILD_TYPE=Release',
                                  '-DBUILD_SHARED_LIBS=ON',
                                  '-DBUILD_TESTING=OFF',
                                  '-DWITH_EXAMPLES=OFF',
                                  '-DWITH_OTLP=ON',
                                  '-DWITH_OTLP_HTTP=ON',
                                  '-DWITH_BENCHMARK=OFF',
                                  "-DCMAKE_PREFIX_PATH={path}".format(path=installed_common_dir),
                                  "-DOTELCPP_PROTO_PATH={path}".format(path=src_dir)])
