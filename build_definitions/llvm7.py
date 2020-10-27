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
import subprocess
import sys
import shutil

from build_definitions import ExtraDownload
from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class LLVM7Dependency(Dependency):
    VERSION = '7.1.0'

    def __init__(self) -> None:
        url_prefix = "http://releases.llvm.org/{0}/"
        super(LLVM7Dependency, self).__init__(
            name='llvm7',
            version=LLVM7Dependency.VERSION,
            url_pattern=url_prefix + 'llvm-{0}.src.tar.xz',
            build_group=BUILD_GROUP_COMMON)
        self.dir_name += ".src"
        self.extra_downloads = [
            ExtraDownload(
                    name='cfe',
                    version=self.version,
                    url_pattern=url_prefix + 'cfe-{0}.src.tar.xz',
                    dir_name='tools',
                    post_exec=['mv', 'cfe-{}.src'.format(self.version), 'cfe']),
            ExtraDownload(
                    name='compiler-rt',
                    version=self.version,
                    url_pattern=url_prefix + 'compiler-rt-{0}.src.tar.xz',
                    dir_name='projects',
                    post_exec=['mv', 'compiler-rt-{}.src'.format(self.version), 'compiler-rt']),
            ExtraDownload(
                    name='clang-tools-extra',
                    version=self.version,
                    url_pattern=url_prefix + 'clang-tools-extra-{0}.src.tar.xz',
                    dir_name='tools/cfe/tools',
                    post_exec=['mv', 'clang-tools-extra-{}.src'.format(self.version), 'extra']),
        ]

        self.copy_sources = False

    def get_prefix(self, builder: BuilderInterface) -> str:
        return builder.get_prefix_with_qualifier(qualifier='llvm7')

    def build(self, builder: BuilderInterface) -> None:
        prefix = self.get_prefix(builder)
        log("Prefix for LLVM 7 build: %s", prefix)
        if os.path.basename(prefix) == 'common':
            raise ValueError("LLVM 7 cannot be installed together with other 'common' dependencies")

        # The LLVM build can fail if a different version is already installed
        # in the install prefix. It will try to link against that version instead
        # of the one being built.
        subprocess.check_call(
                "rm -Rf {0}/include/{{llvm*,clang*}} {0}/lib/lib{{LLVM,LTO,clang}}* {0}/lib/clang/ "
                "{0}/lib/cmake/{{llvm,clang}}".format(prefix),
                shell=True)

        python_executable = shutil.which('python')
        if python_executable is None:
            fatal("Could not find Python -- needed to build LLVM.")

        cxx_flags = builder.compiler_flags + builder.cxx_flags + builder.ld_flags
        if '-g' in cxx_flags:
            cxx_flags.remove('-g')

        cmake_args = [
                '-DCMAKE_BUILD_TYPE=Release',
                '-DLLVM_INCLUDE_DOCS=OFF',
                '-DLLVM_INCLUDE_EXAMPLES=OFF',
                '-DLLVM_INCLUDE_TESTS=OFF',
                '-DLLVM_INCLUDE_UTILS=OFF',
                # If we try to turn shared libs on, the LLVMTestingSupport library will fail to
                # build because it can't find gtest.
                '-DBUILD_SHARED_LIBS=OFF',
                '-DLLVM_TARGETS_TO_BUILD=X86',
                '-DLLVM_ENABLE_RTTI=ON',
                '-DCMAKE_CXX_FLAGS={}'.format(" ".join(cxx_flags)),
                '-DPYTHON_EXECUTABLE={}'.format(python_executable),
                '-DCLANG_BUILD_EXAMPLES=OFF',
                # Turn off any remaining test-related flags.
                '-DCLANG_TOOL_ARCMT_TEST_BUILD=OFF',
                '-DCLANG_TOOL_C_ARCMT_TEST_BUILD=OFF',
                '-DCLANG_TOOL_C_INDEX_TEST_BUILD=OFF',
                '-DCLANG_TOOL_CLANG_IMPORT_TEST_BUILD=OFF',
                '-DCOMPILER_RT_CAN_EXECUTE_TESTS=OFF',
                '-DLLVM_INCLUDE_GO_TESTS=OFF',
                '-DLLVM_TOOL_LLVM_C_TEST_BUILD=OFF',
        ]
        builder.build_with_cmake(self,
                                 cmake_args,
                                 use_ninja_if_available=True)

        create_symlink_at = os.path.join(builder.tp_dir, 'clang-toolchain')
        if os.path.exists(create_symlink_at) and not os.path.islink(create_symlink_at):
            raise IOError(f"File already exists and is not a symlink: {create_symlink_at}")
        remove_path(create_symlink_at)

        create_symlink_to = os.path.relpath(prefix, builder.tp_dir)
        if not os.path.exists(prefix) or not os.path.isdir(prefix):
            raise IOError("Path does not exist or is not a directory: '%s'" % prefix)
        log("Creating symlink %s -> %s (current directory is %d)",
            create_symlink_at, create_symlink_to, os.getcwd())
        os.symlink(create_symlink_to, create_symlink_at)

    def should_build(self, builder: BuilderInterface) -> bool:
        return builder.will_need_clang()
