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
            '1.20.1',
            'https://kerberos.org/dist/krb5/1.20/krb5-{0}.tar.gz',
            BUILD_GROUP_INSTRUMENTED)
        self.patches = ['krb5-1.19.3-use-ldflags-for-test.patch']
        self.patch_strip = 0
        self.copy_sources = True
        self.shared_and_static = True

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        flags: List[str] = list(super().get_additional_ld_flags(builder))
        if builder.compiler_choice.is_linux_clang():
            if builder.build_type == BUILD_TYPE_ASAN:
                # Needed to find dlsym.
                flags.append('-ldl')
        return flags

    def get_additional_compiler_flags(self, builder: 'BuilderInterface') -> List[str]:
        flags: List[str] = list(super().get_additional_compiler_flags(builder))
        # This is needed to avoid duplicate symbol errors during static linking.
        flags.append('-fcommon')
        return flags

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: BuilderInterface) -> Set[str]:
        return {'-Wl,--no-undefined'}

    def build(self, builder: BuilderInterface) -> None:
        # krb5 does not support building shared and static libraries at the same time.
        linking_types = ['shared']
        if is_linux():
            # krb5 static build of version 1.19.3 has some issues on macOS:
            # https://gist.githubusercontent.com/mbautin/2f71c26bf388c720e5abbf9b8903419d/raw
            # Only build static libs on Linux for now, because we only need them on Linux for LTO.
            linking_types.append('static')

        for linking_type in linking_types:
            build_dir = os.path.join(os.getcwd(), linking_type)
            with PushDir(build_dir):
                log(f"Building krb5 with {linking_type} linking in {os.getcwd()}")
                if linking_type == 'shared':
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
                log(f"Finished building krb5 with {linking_type} linking in {os.getcwd()}")
