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

from build_definitions.libcxx10base import LibCxx10BaseDependency

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class LibCxx10Dependency(LibCxx10BaseDependency):
    def __init__(self) -> None:
        super(LibCxx10Dependency, self).__init__('libcxx10')

    def build(self, builder: BuilderInterface) -> None:
        llvm_src_path = builder.source_path(self)

        prefix = os.path.join(builder.prefix, 'libcxx10')

        args = [
            '-DCMAKE_BUILD_TYPE=Release',
            '-DLLVM_ENABLE_PROJECTS=libcxx;libcxxabi',
            '-DLIBCXXABI_LIBCXX_PATH=%s' % os.path.join(llvm_src_path, 'libcxx'),
            '-DLLVM_TARGETS_TO_BUILD=X86',
            '-DBUILD_SHARED_LIBS=ON',
            '-DLLVM_ENABLE_RTTI=ON',
            '-DLIBUNWIND_USE_COMPILER_RT=ON',
            '-DCMAKE_INSTALL_PREFIX={}'.format(prefix),
            '-DLIBCXXABI_USE_COMPILER_RT=ON',
            '-DLIBCXXABI_USE_LLVM_UNWINDER=ON',
            '-DLIBCXX_USE_COMPILER_RT=ON',
            '-DLLVM_PATH=%s' % llvm_src_path,
        ]

        builder.build_with_cmake(
            self,
            extra_args=args,
            src_subdir_name='libcxx',
            use_ninja_if_available=True)
