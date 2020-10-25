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


class LLVMDependency(Dependency):
    VERSION = '7.1.0'

    def __init__(self) -> None:
        url_prefix = "http://releases.llvm.org/{0}/"
        super(LLVMDependency, self).__init__(
            name='llvm',
            version=LLVMDependency.VERSION,
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

    def build(self, builder: BuilderInterface) -> None:
        prefix = builder.get_prefix('llvm7')

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
                #'-DCMAKE_INSTALL_PREFIX={}'.format(prefix),
                '-DLLVM_INCLUDE_DOCS=OFF',
                '-DLLVM_INCLUDE_EXAMPLES=OFF',
                '-DLLVM_INCLUDE_TESTS=OFF',
                '-DLLVM_INCLUDE_UTILS=OFF',
                '-DLLVM_TARGETS_TO_BUILD=X86',
                '-DLLVM_ENABLE_RTTI=ON',
                '-DCMAKE_CXX_FLAGS={}'.format(" ".join(cxx_flags)),
                '-DPYTHON_EXECUTABLE={}'.format(python_executable),
                '-DCLANG_BUILD_EXAMPLES=ON'
        ]
        builder.build_with_cmake(self,
                                 cmake_args,
                                 use_ninja_if_available=True)

        link_path = os.path.join(builder.tp_dir, 'clang-toolchain')
        remove_path(link_path)
        list_dest = os.path.relpath(prefix, builder.tp_dir)
        log("Link %s => %s", link_path, list_dest)
        os.symlink(list_dest, link_path)

    def should_build(self, builder: BuilderInterface) -> bool:
        return builder.will_need_clang()
