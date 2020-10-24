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

from build_definitions import BUILD_TYPE_ASAN, BUILD_TYPE_TSAN

from yugabyte_db_thirdparty.util import replace_string_in_file

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


LIBCXX_LLVM_VERSION = '10.0.1'


class LibCxx10BaseDependency(Dependency):
    def __init__(self, name: str) -> None:
        super(LibCxx10BaseDependency, self).__init__(
            name=name,
            version=LIBCXX_LLVM_VERSION,
            url_pattern='https://github.com/llvm/llvm-project/archive/llvmorg-{}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)

    def postprocess_ninja_build_file(
            self,
            builder: BuilderInterface,
            ninja_build_file_path: str) -> None:
        super().postprocess_ninja_build_file(builder, ninja_build_file_path)
        if builder.build_type not in [BUILD_TYPE_ASAN, BUILD_TYPE_TSAN]:
            return

        removed_string = '-lstdc++'
        num_lines_modified = replace_string_in_file(
            path=ninja_build_file_path,
            str_to_replace=removed_string,
            str_to_replace_with='')
        log("Modified %d lines in file %s: removed '%s'",
            num_lines_modified, os.path.abspath(ninja_build_file_path), removed_string)

    def get_additional_ld_flags(self, builder: 'BuilderInterface') -> List[str]:
        if builder.build_type not in [BUILD_TYPE_ASAN, BUILD_TYPE_TSAN]:
            return []

        return ['-ldl', '-lpthread', '-lm', '-lstdc++']

    # def build(self, builder: BuilderInterface) -> None:
    #     llvm_src_path = builder.source_path(self)

    #     prefix = os.path.join(builder.prefix, 'libcxx10')

    #     args = [
    #         '-DCMAKE_BUILD_TYPE=Release',
    #         '-DLLVM_ENABLE_PROJECTS=libcxx;libcxxabi',
    #         '-DLIBCXXABI_LIBCXX_PATH=%s' % os.path.join(llvm_src_path, 'libcxx'),
    #         '-DLLVM_TARGETS_TO_BUILD=X86',
    #         '-DBUILD_SHARED_LIBS=ON',
    #         '-DLLVM_ENABLE_RTTI=ON',
    #         '-DLIBUNWIND_USE_COMPILER_RT=ON',
    #         '-DCMAKE_INSTALL_PREFIX={}'.format(prefix),
    #         '-DLIBCXXABI_USE_COMPILER_RT=ON',
    #         '-DLIBCXXABI_USE_LLVM_UNWINDER=ON',
    #         '-DLIBCXX_USE_COMPILER_RT=ON',
    #         '-DLLVM_PATH=%s' % llvm_src_path,
    #     ]

    #     builder.build_with_cmake(
    #         self,
    #         extra_args=args,
    #         src_subdir_name='libcxx',
    #         use_ninja_if_available=True)
