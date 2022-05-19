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


class Krb5Dependency(Dependency):
    def __init__(self) -> None:
        super(Krb5Dependency, self).__init__(
            'krb5',
            '1.19.3',
            'https://kerberos.org/dist/krb5/1.19/krb5-{0}.tar.gz',
            BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True
        self.patches = ['krb5-1.19.3-use-ldflags-for-test.patch']
        self.patch_strip = 0

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        flags: List[str] = super().get_additional_ld_flags(builder)
        if builder.compiler_choice.is_linux_clang():
            if builder.build_type == BUILD_TYPE_ASAN:
                # Needed to find dlsym.
                flags.append('-ldl')
        return flags

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: BuilderInterface) -> Set[str]:
        return {'-Wl,--no-undefined'}

    def build(self, builder: BuilderInterface) -> None:
        # krb5 does not support building shared and static libraries at the same time.
        for is_shared in [False, True]:
            if is_shared:
                extra_args = ['--enable-shared', '--disable-static']
            else:
                extra_args = ['--disable-shared', '--enable-static']
            if builder.build_type in [BUILD_TYPE_ASAN]:
                extra_args.append('--enable-asan')
            builder.build_with_configure(
                dep=self,
                src_subdir_name='src',
                extra_args=extra_args,
            )
