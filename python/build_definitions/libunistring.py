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


class LibUnistringDependency(Dependency):
    def __init__(self) -> None:
        super(LibUnistringDependency, self).__init__(
            'libunistring',
            '1.0',
            'https://ftp.gnu.org/gnu/libunistring/libunistring-{0}.tar.gz',
            BuildGroup.COMMON)
        self.copy_sources = True

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: BuilderInterface) -> Set[str]:
        if is_macos():
            return {'-lrt'}
        return set()

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(dep=self)

    def use_cppflags_env_var(self) -> bool:
        return True
