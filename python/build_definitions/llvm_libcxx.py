# Copyright (c) Yugabyte, Inc.
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
import sys_detection

from build_definitions.llvm_part import LlvmPartDependencyBase
from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa
from yugabyte_db_thirdparty.util import replace_string_in_file


class LlvmLibCxxDependencyBase(LlvmPartDependencyBase):
    def __init__(self, name: str, version: str) -> None:
        super(LlvmLibCxxDependencyBase, self).__init__(
            name=name,
            version=version,
            build_group=BUILD_GROUP_INSTRUMENTED)

    def postprocess_ninja_build_file(
            self,
            builder: BuilderInterface,
            ninja_build_file_path: str) -> None:
        super().postprocess_ninja_build_file(builder, ninja_build_file_path)
        if not builder.compiler_choice.is_linux_clang():
            return

        if builder.build_type not in [BUILD_TYPE_ASAN, BUILD_TYPE_TSAN]:
            return

        removed_string = '-lstdc++'
        num_lines_modified = replace_string_in_file(
            path=ninja_build_file_path,
            str_to_replace=removed_string,
            str_to_replace_with='')
        log("Modified %d lines in file %s: removed '%s'",
            num_lines_modified, os.path.abspath(ninja_build_file_path), removed_string)

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        # This workaround is needed for both LLVM 10 and LLVM 11.
        if (builder.compiler_choice.is_linux_clang() and
                builder.build_type in [BUILD_TYPE_ASAN, BUILD_TYPE_TSAN]):
            # We need to link with these libraries in ASAN because otherwise libc++ CMake
            # configuration step fails and some C standard library functions cannot be found.
            # However, we then remove -lstdc++ from the generated build.ninja file (see
            # postprocess_ninja_build_file). The other libraries (-ldl, -lpthread, and -lm) are OK
            # to keep.
            return ['-ldl', '-lpthread', '-lm', '-lstdc++']

        return []

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: BuilderInterface) -> Set[str]:
        if builder.build_type == BUILD_TYPE_ASAN:
            # We need to be able to ignore undefined symbols because ASAN runtime library will be
            # linked statically to each executable.
            return {'-Wl,-z,defs'}
        return set()

    def get_install_prefix(self, builder: BuilderInterface) -> str:
        return os.path.join(builder.prefix, 'libcxx')

    def build(self, builder: BuilderInterface) -> None:
        llvm_src_path = builder.fs_layout.get_source_path(self)

        args = [
            '-DCMAKE_BUILD_TYPE=Release',
            '-DBUILD_SHARED_LIBS=ON',
            '-DLLVM_PATH=%s' % os.path.join(llvm_src_path, 'llvm'),
        ]

        builder.build_with_cmake(
            self,
            extra_args=args,
            src_subdir_name=self.get_source_subdir_name(),
            use_ninja_if_available=True)

    def get_source_subdir_name(self) -> str:
        raise NotImplementedError()


class LlvmLibCxxAbiDependency(LlvmLibCxxDependencyBase):
    def __init__(self, version: str) -> None:
        super(LlvmLibCxxAbiDependency, self).__init__(
            name='llvm_libcxxabi',
            version=version)

    def get_source_subdir_name(self) -> str:
        return 'libcxxabi'

    def get_additional_cmake_args(self, builder: BuilderInterface) -> List[str]:
        llvm_src_path = builder.fs_layout.get_source_path(self)
        args = [
            '-DLIBCXXABI_LIBCXX_PATH=%s' % os.path.join(llvm_src_path, 'libcxx'),
            '-DLIBCXXABI_USE_COMPILER_RT=ON',
            '-DLIBCXXABI_USE_LLVM_UNWINDER=ON',
        ]
        return args

    def build(self, builder: BuilderInterface) -> None:
        super().build(builder)
        src_include_path = os.path.join(
            builder.fs_layout.get_source_path(self), 'libcxxabi', 'include')
        # Put C++ ABI headers together with libc++ headers.
        dest_include_path = os.path.join(self.get_install_prefix(builder), 'include', 'c++', 'v1')
        mkdir_if_missing(dest_include_path)
        for header_name in ['cxxabi.h', '__cxxabi_config.h']:
            copy_file_and_log(
                os.path.join(src_include_path, header_name),
                os.path.join(dest_include_path, header_name))


class LlvmLibCxxDependency(LlvmLibCxxDependencyBase):
    def __init__(self, version: str) -> None:
        super(LlvmLibCxxDependency, self).__init__(
            name='llvm_libcxx',
            version=version)

    def get_source_subdir_name(self) -> str:
        return 'libcxx'

    def get_additional_cmake_args(self, builder: BuilderInterface) -> List[str]:
        return [
            '-DLIBCXX_USE_COMPILER_RT=ON',
            '-DLIBCXX_ENABLE_RTTI=ON',
            '-DLIBCXX_CXX_ABI=libcxxabi',
            '-DLIBCXXABI_USE_LLVM_UNWINDER=ON',
        ]


class LibCxxWithAbiDependency(LlvmLibCxxDependencyBase):
    """
    A combined dependency for libc++ and libc++abi.

    Using the approach described at:

    https://libcxx.llvm.org/BuildingLibcxx.html

    Based on the following instructions:

    $ git clone https://github.com/llvm/llvm-project.git
    $ cd llvm-project
    $ mkdir build
    $ cmake -G Ninja -S runtimes -B build -DLLVM_ENABLE_RUNTIMES="libcxx;libcxxabi;libunwind"
    $ ninja -C build cxx cxxabi unwind
    $ ninja -C build check-cxx check-cxxabi check-unwind
    $ ninja -C build install-cxx install-cxxabi install-unwind

    Using this with LLVM/Clang 13 or later.
    """

    def __init__(self, version: str) -> None:
        super(LibCxxWithAbiDependency, self).__init__(
            name='llvm_libcxx_with_abi',
            version=version)

    def get_source_subdir_name(self) -> str:
        return 'runtimes'

    def get_additional_cmake_args(self, builder: BuilderInterface) -> List[str]:
        args = ['-DLLVM_ENABLE_RUNTIMES=libcxx;libcxxabi']
        if builder.build_type == BUILD_TYPE_TSAN:
            local_sys_conf = sys_detection.local_sys_conf()
            if local_sys_conf.is_redhat_family() and int(local_sys_conf.short_os_version()) == 7:
                # On CentOS 7, we want to prevent libcxxabi build system from deciding that the
                # platform already has an implementation of __cxa_thread_atexit_impl. Instead,
                # it should still use the weak symbol.
                # See https://github.com/yugabyte/yugabyte-db/issues/13615 for details.
                args.append('-DLIBCXXABI_HAS_CXA_THREAD_ATEXIT_IMPL=OFF')
        return args

    def get_compiler_wrapper_ld_flags_to_append(self, builder: 'BuilderInterface') -> List[str]:
        extra_ld_flags = super().get_compiler_wrapper_ld_flags_to_append(builder)
        if builder.build_type == BUILD_TYPE_TSAN:
            # It is not clear why in Clang 13 this suddenly becomes necessary in order to avoid
            # failing with undefined TSAN-related symbols while linking shared libraries.
            extra_ld_flags.append('-Wl,--unresolved-symbols=ignore-all')
        return extra_ld_flags
