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


class LibUvDependency(Dependency):
    def __init__(self) -> None:
        super(LibUvDependency, self).__init__(
            name='libuv',
            version='1.23.0',
            url_pattern='https://github.com/libuv/libuv/archive/v{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(
            self,
            [
                '-DCMAKE_BUILD_TYPE={}'.format(
                    builder.cmake_build_type_for_test_only_dependencies()),
                '-DBUILD_SHARED_LIBS=ON'
            ] + builder.get_openssl_related_cmake_args())
