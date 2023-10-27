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
import multiprocessing

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class GLogDependency(Dependency):
    def __init__(self) -> None:
        super(GLogDependency, self).__init__(
            name='glog',
            version='0.4.0-yb-6',
            url_pattern='https://github.com/yugabyte/glog/archive/v{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.patch_version = 1
        self.patch_strip = 0
        self.patches = ['glog-tsan-annotations.patch',
                        'glog-symbolize-and-demangle.patch']
        self.post_patch = ['autoreconf', '-fvi']

    def get_additional_cmake_args(self, builder: BuilderInterface) -> List[str]:
        cmake_args = [
            '-DCMAKE_BUILD_TYPE=Release',
        ]
        if builder.build_type in [BuildType.ASAN, BuildType.TSAN]:
            # Can't build glog unit tests in ASAN/TSAN because of their overrides of new/delete.
            # We could patch glog to support that at some point.
            cmake_args += ['-DBUILD_TESTING=OFF']
        return cmake_args

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        if builder.compiler_choice.is_linux_clang() and builder.build_type in [
                BuildType.ASAN, BuildType.TSAN]:
            # Without this, getting undefined symbols:
            # - pthread_rwlock_destroy
            # - pthread_rwlock_init
            # - pthread_rwlock_unlock
            # - pthread_rwlock_wrlock
            return ['-lpthread']
        return []

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(dep=self, shared_and_static=True)
