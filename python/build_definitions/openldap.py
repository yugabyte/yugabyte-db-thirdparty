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


class OpenLDAPDependency(Dependency):
    def __init__(self) -> None:
        super(OpenLDAPDependency, self).__init__(
              'openldap',
              '2_4_54',
              'https://github.com/yugabyte/openldap/archive/OPENLDAP_REL_ENG_{}.tar.gz',
              BUILD_GROUP_COMMON)
        self.copy_sources = True
        self.patch_version = 1
        self.patches = ['openldap-do-not-build-docs.patch']

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        llvm_major_version = builder.compiler_choice.get_llvm_major_version()
        flags = []
        linux_llvm15_or_later = (
            is_linux() and llvm_major_version is not None and llvm_major_version >= 15)

        if is_macos() or linux_llvm15_or_later:
            # To avoid this error with Clang 15 on Linux:
            # https://gist.githubusercontent.com/mbautin/a9ca659ec5955ecb0e3d469376659c2b/raw
            flags.append('-Wno-error=implicit-function-declaration')

        if linux_llvm15_or_later:
            # See the links for the errors with Clang 15 on Linux that make the corresponding
            # -Wno-error=... flags necessary.
            flags.extend([
                # https://gist.githubusercontent.com/mbautin/354c8882998067a87ec8c832d454603f/raw
                '-Wno-error=implicit-int',
                # https://gist.githubusercontent.com/mbautin/b8b022cedd1bd34bbf82576e1972a22f/raw
                '-Wno-error=int-conversion'
            ])
        return flags

    def build(self, builder: BuilderInterface) -> None:
        # build client only
        disabled_features = (
            'slapd', 'bdb', 'hdb', 'mdb', 'monitor', 'relay', 'syncprov'
        )

        builder.build_with_configure(
            dep=self,
            extra_args=['--disable-' + feature for feature in disabled_features] +
                       ['--with-cyrus-sasl=no'])

    def use_cppflags_env_var(self) -> bool:
        return True
