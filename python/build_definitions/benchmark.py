#
# Copyright (c) YugabyteDB, Inc.
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


class BenchmarkDependency(Dependency):
    def __init__(self) -> None:
        super(BenchmarkDependency, self).__init__(
            name='benchmark',
            version='1.9.5',
            url_pattern='https://github.com/google/benchmark/archive/refs/tags/v{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        extra_cmake_args = [
            '-DCMAKE_BUILD_TYPE=Release',
            # Testing would pull in and build a bundled googletest.
            '-DBENCHMARK_ENABLE_TESTING=OFF',
            '-DBENCHMARK_ENABLE_GTEST_TESTS=OFF',
            # Do not let new compiler warnings break the build.
            '-DBENCHMARK_ENABLE_WERROR=OFF',
            '-DBENCHMARK_INSTALL_DOCS=OFF',
        ]
        builder.build_with_cmake(self, shared_and_static=True, extra_cmake_args=extra_cmake_args)
