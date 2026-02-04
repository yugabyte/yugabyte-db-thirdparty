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


class HwyDependency(Dependency):
    def __init__(self) -> None:
        super(HwyDependency, self).__init__(
            name='hwy',
            version='1.3.0',
            url_pattern='https://github.com/google/highway/archive/refs/tags/'
                        '{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        # set(HWY_ENABLE_TESTS ON CACHE BOOL "Enable HWY tests")
        # disable tests by default
        extra_cmake_args = [
            '-DHWY_ENABLE_TESTS=OFF',
        ]
        builder.build_with_cmake(self, shared_and_static=True, extra_cmake_args=extra_cmake_args)
