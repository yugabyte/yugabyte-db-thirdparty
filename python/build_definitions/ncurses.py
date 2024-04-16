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
from yugabyte_db_thirdparty.linuxbrew import using_linuxbrew


class NCursesDependency(Dependency):
    def __init__(self) -> None:
        super(NCursesDependency, self).__init__(
            'ncurses',
            '6.3',
            'https://ftp.gnu.org/pub/gnu/ncurses/ncurses-{0}.tar.gz',
            BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        extra_args = ['--with-shared', '--with-default-terminfo-dir=/usr/share/terminfo']
        builder.build_with_configure(dep=self, extra_configure_args=extra_args)

    def get_additional_leading_ld_flags(self, builder: 'BuilderInterface') -> List[str]:
        flags = super().get_additional_leading_ld_flags(builder)

        # We need to put the ../lib directory in front of the linker flags so that
        # Linuxbrew-provided ncurses does not take over.
        if using_linuxbrew():
            flags.append('-L../lib')
        return flags

    def use_cppflags_env_var(self) -> bool:
        return True
