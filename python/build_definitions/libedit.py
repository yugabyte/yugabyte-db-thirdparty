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


class LibEditDependency(Dependency):
    def __init__(self) -> None:
        super(LibEditDependency, self).__init__(
              name='libedit',
              version='20191231-3.1',
              url_pattern='https://github.com/yugabyte/libedit/archive/libedit-{}.tar.gz',
              build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        flags = ['-I%s' % os.path.join(builder.prefix_include, 'ncurses')]
        llvm_major_version = builder.compiler_choice.get_llvm_major_version()
        if (builder.compiler_choice.is_linux_clang() and
                builder.build_type == BuildType.ASAN and
                llvm_major_version is not None and
                llvm_major_version >= 16):
            flags.append('-Wno-error=implicit-function-declaration')
        return flags

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(dep=self, extra_configure_args=['--with-pic'])

    def use_cppflags_env_var(self) -> bool:
        return True
