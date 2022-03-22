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

import platform

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class CRCUtilDependency(Dependency):
    def __init__(self) -> None:
        super(CRCUtilDependency, self).__init__(
            name='crcutil',
            version='v20210630-8678969f02c4679fa40abaa9c5d7afadec50ed84',
            url_pattern='https://github.com/yugabyte/crcutil/archive/refs/tags/{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True
        self.patch_version = 1
        self.patch_strip = 0
        self.patches = ['crcutil-fix-offsetof.patch']

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        if (builder.compiler_choice.compiler_type == 'gcc' and
                platform.uname().processor == 'x86_64'):
            # -mcrc32 (https://gcc.gnu.org/onlinedocs/gcc/x86-Options.html)
            # This option enables built-in functions __builtin_ia32_crc32qi, __builtin_ia32_crc32hi,
            # __builtin_ia32_crc32si and __builtin_ia32_crc32di to generate the crc32 machine
            # instruction.
            return ['-mcrc32']
        return []

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        log_output(log_prefix, ['./autogen.sh'])
        builder.build_with_configure(
            log_prefix=log_prefix
        )
