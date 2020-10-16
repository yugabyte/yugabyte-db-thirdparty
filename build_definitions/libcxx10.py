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

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from build_definitions import *  # noqa


class LibCxx10Dependency(Dependency):
    def __init__(self) -> None:
        super(LibCxx10Dependency, self).__init__(
            name='libcxx10',
            version='10.0.1',
            url_pattern='https://github.com/llvm/llvm-project/archive/llvmorg-{}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)

    def build(self, builder: BuilderInterface) -> None:
        llvm_src_path = builder.source_path(self)

        ld_flags = [
            flag for flag in builder.ld_flags
            if flag not in ['-lc++', '-lc++abi']
        ]
        ld_flags_str = ' '.join(ld_flags)

        cxx_flags = [
            flag for flag in builder.cxx_flags
            if flag not in ['-stdlib=libc++']
        ]
        cxx_flags_str = ' '.join(cxx_flags)

        args = [
            '-DCMAKE_BUILD_TYPE=Release',
            '-DLLVM_ENABLE_PROJECTS=libcxx;libcxxabi',
            '-DLIBCXXABI_LIBCXX_PATH=%s' % os.path.join(llvm_src_path, 'libcxx'),
            '-DLLVM_TARGETS_TO_BUILD=X86',
            '-DBUILD_SHARED_LIBS=ON',
            '-DLLVM_ENABLE_RTTI=ON',
            '-DLIBUNWIND_USE_COMPILER_RT=ON',
            '-DLLVM_PATH=%s' % llvm_src_path,
            '-DCMAKE_INSTALL_PREFIX={}'.format(builder.prefix),
            '-DLIBCXXABI_USE_COMPILER_RT=ON',
            '-DLIBCXXABI_USE_LLVM_UNWINDER=ON',
            '-DLIBCXX_USE_COMPILER_RT=ON',
            '-DCMAKE_CXX_FLAGS={}'.format(cxx_flags_str),
            '-DCMAKE_MODULE_LINKER_FLAGS={}'.format(linker_flags_str),
            '-DCMAKE_SHARED_LINKER_FLAGS={}'.format(linker_flags_str),
            '-DCMAKE_STATIC_LINKER_FLAGS={}'.format(linker_flags_str),
        ]
        if builder.build_type == BUILD_TYPE_ASAN:
            args.append("-DLLVM_USE_SANITIZER=Address;Undefined")
        elif builder.build_type == BUILD_TYPE_TSAN:
            args.append("-DLLVM_USE_SANITIZER=Thread")

        builder.build_with_cmake(
            self,
            extra_args=args,
            src_subdir_name='llvm',
            use_ninja_if_available=True,
            extra_build_tool_args=['libcxxabi', 'libcxx'])
        # builder.build_with_cmake(
        #     self,
        #     extra_args=args,
        #     src_subdir_name='libcxx')