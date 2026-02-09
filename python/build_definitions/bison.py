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


class BisonDependency(Dependency):
    def __init__(self) -> None:
        super(BisonDependency, self).__init__(
            name='bison',
            version='3.4.1',
            url_pattern='https://ftp.gnu.org/gnu/bison/bison-{0}.tar.gz',
            build_group=BuildGroup.COMMON,
            license='GPL-3.0')
        self.copy_sources = True

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        llvm_major_version = builder.compiler_choice.get_llvm_major_version()
        flags = []
        llvm_installer_16_or_later = (
            builder.compiler_choice.is_llvm_installer_clang() and
            llvm_major_version is not None and llvm_major_version >= 16)

        if (is_macos() or llvm_installer_16_or_later):
            # To avoid this error in Bison 3.4.1 build:
            # lib/obstack.c:351:31: error: incompatible function pointer types initializing
            # 'void (*)(void) __attribute__((noreturn))' with an expression of type 'void (void)'
            # [-Wincompatible-function-pointer-types]
            flags.append('-Wno-error=incompatible-function-pointer-types')
        return flags

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(dep=self, extra_configure_args=['--with-pic'])

    def use_cppflags_env_var(self) -> bool:
        return True
