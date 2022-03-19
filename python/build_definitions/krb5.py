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
            '1.19.3-yb-1',
            'https://github.com/yugabyte/krb5/archive/refs/tags/krb5-{0}.tar.gz',
            BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        flags: List[str] = super().get_additional_ld_flags(builder)
        if builder.build_type == BUILD_TYPE_ASAN:
            # Needed to find dlsym.
            flags.append('-ldl')
            # if builder.compiler_choice.get_llvm_major_version() >= 13:
            #     flags.append('-Wl,--allow-shlib-undefined')
            # if (builder.build_type == BUILD_TYPE_TSAN and
            #         builder.compiler_choice.get_llvm_major_version() >= 13):

            #     # https://gist.githubusercontent.com/mbautin/6b096645d7bbc89f25fde2a6942fc71b/raw
            #     flags.append('-lunwind')
        return flags

    # def get_compiler_wrapper_ld_flags_to_append(self, builder: BuilderInterface) -> List[str]:
    #     if builder.build_type == BUILD_TYPE_ASAN:
    #         return ['-fsanitize=address']
    #     return []

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: BuilderInterface) -> Set[str]:
        return {'-Wl,--no-undefined'}

    def build(self, builder: BuilderInterface) -> None:
        extra_args = []
        if builder.build_type in [BUILD_TYPE_ASAN]:
            extra_args.append('--enable-asan')
        builder.build_with_configure(
            log_prefix=builder.log_prefix(self),
            src_subdir_name='src',
            extra_args=extra_args,
            autoconf=True,
        )
