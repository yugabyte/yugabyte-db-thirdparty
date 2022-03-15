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
            '1.19.2',
            'https://kerberos.org/dist/krb5/1.19/krb5-{0}.tar.gz',
            BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        if builder.compiler_choice.is_linux_clang1x() and builder.build_type == BUILD_TYPE_ASAN:
            # Needed to find dlsym.
            return ['-ldl']
        return []

    def build(self, builder: BuilderInterface) -> None:
        extra_args = []
        if builder.build_type in [BUILD_TYPE_ASAN]:
            extra_args.append('--enable-asan')
        builder.build_with_configure(
            log_prefix=builder.log_prefix(self),
            src_subdir_name='src',
            extra_args=extra_args,
        )
