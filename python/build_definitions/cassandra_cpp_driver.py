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


# C++ Cassandra driver
class CassandraCppDriverDependency(Dependency):
    def __init__(self) -> None:
        super(CassandraCppDriverDependency, self).__init__(
                'cassandra-cpp-driver', '2.9.0-yb-13',
                'https://github.com/yugabyte/cassandra-cpp-driver/archive/{0}.tar.gz',
                BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = False
        self.patch_version = 0

    def build(self, builder: BuilderInterface) -> None:
        if not is_macos():
            # TODO: refactor to polymorphism.
            builder.prepend_rpath(os.path.join(
                builder.fs_layout.tp_installed_common_dir, "lib"))

        # FindOpenSSL.cmake in cassandra-cpp-driver is buggy (e.g. it cannot recognize the version
        # 1.1.1g of OpenSSL, because it has a regexp hardcoded with [a-f], as if for hex characters,
        # and we prefer to use the standard version of this file that comes with CMake).
        src_dir = builder.fs_layout.get_source_path(self)
        find_openssl_cmake_module_path = os.path.join(
            src_dir, 'cmake', 'modules', 'FindOpenSSL.cmake')
        if os.path.exists(find_openssl_cmake_module_path):
            log("Removing %s so we can use the standard version of this CMake module",
                find_openssl_cmake_module_path)
            os.remove(find_openssl_cmake_module_path)
        else:
            log("File does not exist, maybe already removed: %s", find_openssl_cmake_module_path)

        cmake_args = [
            '-DCMAKE_BUILD_TYPE={}'.format(builder.cmake_build_type_for_test_only_dependencies()),
            # On macOS, it is important not to use Homebrew-provided libuv.
            '-DLIBUV_ROOT_DIR={}'.format(builder.prefix),
        ] + builder.get_openssl_related_cmake_args()
        builder.build_with_cmake(self, cmake_args)

        fix_shared_library_references(builder.prefix, 'libcassandra')

    def get_additional_cxx_flags(self, builder: 'BuilderInterface') -> List[str]:
        if is_macos():
            return []
        extra_cxx_flags: List[str] = []
        builder.add_checked_flag(extra_cxx_flags, '-Wno-error=implicit-fallthrough')
        builder.add_checked_flag(extra_cxx_flags, '-Wno-error=class-memaccess')
        if builder.compiler_choice.is_linux_clang1x():
            builder.add_checked_flag(extra_cxx_flags, '-Wno-error=unused-command-line-argument')
            builder.add_checked_flag(extra_cxx_flags, '-Wno-error=deprecated-declarations')
        gcc_major_version = builder.compiler_choice.get_gcc_major_version()
        if gcc_major_version is not None and gcc_major_version >= 11:
            # Needed to avoid this error:
            # https://gist.githubusercontent.com/mbautin/d1ce54c995f9e535ab214a12945d2e7b/raw
            extra_cxx_flags.append('-Wno-error=free-nonheap-object')
        return extra_cxx_flags
