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
import multiprocessing
import subprocess
import sys
import build_definitions.llvm

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa
from build_definitions import ExtraDownload


class LibCXXDependency(Dependency):
    def __init__(self) -> None:
        super(LibCXXDependency, self).__init__(
            name='libcxx',
            version=build_definitions.llvm.LLVMDependency.VERSION,
            # This is a special "URL pattern" we support.
            url_pattern='mkdir',
            build_group=BUILD_GROUP_INSTRUMENTED)

        url_prefix = "http://releases.llvm.org/{0}/"

        self.extra_downloads = [
            ExtraDownload(
                name='llvm',
                version=self.version,
                url_pattern=url_prefix + 'llvm-{0}.src.tar.xz',
                dir_name='temp',
                post_exec=[
                    ['rm', '-rf', '../llvm'],
                    ['mv', 'llvm-{}.src'.format(self.version), '../llvm']
                ]),
            ExtraDownload(
                name='libcxx',
                version=self.version,
                url_pattern=url_prefix + 'libcxx-{0}.src.tar.xz',
                dir_name='temp',
                post_exec=['mv', 'libcxx-{}.src'.format(self.version), '../llvm/projects/libcxx']),
            ExtraDownload(
                name='libcxxabi',
                version=self.version,
                url_pattern=url_prefix + 'libcxxabi-{0}.src.tar.xz',
                dir_name='temp',
                post_exec=['mv', 'libcxxabi-{}.src'.format(self.version),
                           '../llvm/projects/libcxxabi']),
        ]
        self.copy_sources = False

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        prefix = os.path.join(builder.prefix, 'libcxx')
        os.environ["YB_REMOTE_COMPILATION"] = "0"

        remove_path('CMakeCache.txt')
        remove_path('CMakeFiles')

        args = [
            'cmake',
            os.path.join(builder.get_source_path(self), 'llvm'),
            '-DCMAKE_BUILD_TYPE=Release',
            '-DLLVM_TARGETS_TO_BUILD=X86',
            '-DLLVM_ENABLE_RTTI=ON',
            '-DCMAKE_CXX_FLAGS={}'.format(" ".join(builder.ld_flags)),
        ]
        if builder.build_type == BUILD_TYPE_ASAN:
            args.append("-DLLVM_USE_SANITIZER=Address;Undefined")
        elif builder.build_type == BUILD_TYPE_TSAN:
            args.append("-DLLVM_USE_SANITIZER=Thread")

        log_output(log_prefix, args)
        log_output(
                log_prefix,
                ['make', '-j{}'.format(multiprocessing.cpu_count()), 'install-libcxxabi',
                 'install-libcxx'])

        # libcxx-5.0.0 contains bug, cxxabi.h is installed with non existing component
        subprocess.check_call(
                "cp projects/libcxx/include/c++build/* {}/include/c++/v1".format(prefix),
                shell=True)

    def should_build(self, builder: BuilderInterface) -> bool:
        return builder.building_with_clang()
