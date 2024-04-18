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


class LibUuidDependency(Dependency):
    def __init__(self) -> None:
        super(LibUuidDependency, self).__init__(
            name='libuuid',
            version='1.0.3',
            url_pattern='https://github.com/yugabyte/libuuid/archive/libuuid-{0}.tar.gz',
            build_group=BuildGroup.COMMON)
        self.copy_sources = True

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        llvm_major_version = builder.compiler_choice.get_llvm_major_version()
        linux_llvm15_or_later = (
            is_linux() and llvm_major_version is not None and llvm_major_version >= 15)
        flags = []
        if linux_llvm15_or_later:
            # https://gist.githubusercontent.com/mbautin/9ae79d6c81adaa68746287458cac4d10/raw
            flags.append('-Wno-error=implicit-function-declaration')

        return flags

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(
            dep=self, extra_configure_args=['--with-pic'], run_autoreconf=True)
