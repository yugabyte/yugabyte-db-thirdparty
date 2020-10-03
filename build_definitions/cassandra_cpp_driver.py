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

from yugabyte_db_thirdparty.builder_interface import BuilderInterface
from build_definitions import *  # noqa


# C++ Cassandra driver
class CassandraCppDriverDependency(Dependency):
    def __init__(self) -> None:
        super(CassandraCppDriverDependency, self).__init__(
                'cassandra-cpp-driver', '2.9.0-yb-8',
                'https://github.com/YugaByte/cassandra-cpp-driver/archive/{0}.tar.gz',
                BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = False
        self.patch_version = 0
        self.patch_strip = 1

    def build(self, builder: BuilderInterface) -> None:
        cxx_flags = []
        if not is_mac():
            # TODO: this will modify rpath and flags not just for this dependency but for all
            #       dependencies that are built after it as well.
            builder.prepend_rpath(os.path.join(builder.tp_installed_common_dir, "lib"))
            cxx_flags = builder.compiler_flags + builder.cxx_flags + builder.ld_flags
            builder.add_checked_flag(cxx_flags, '-Wno-error=implicit-fallthrough')
            builder.add_checked_flag(cxx_flags, '-Wno-error=class-memaccess')

        # FindOpenSSL.cmake in cassandra-cpp-driver is buggy (e.g. it cannot recognize the version
        # 1.1.1g of OpenSSL, because it has a regexp hardcoded with [a-f], as if for hex characters,
        # and we prefer to use the standard version of this file that comes with CMake).
        src_dir = builder.source_path(self)
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
            '-DCMAKE_POSITION_INDEPENDENT_CODE=On',
            '-DCMAKE_INSTALL_PREFIX={}'.format(builder.prefix),
            '-DBUILD_SHARED_LIBS=On'
        ] + (
            ['-DCMAKE_CXX_FLAGS=' + ' '.join(cxx_flags)] if not is_mac() else []
        ) + (
            builder.get_openssl_related_cmake_args()
        )
        builder.build_with_cmake(self, cmake_args)

        if is_mac():
            lib_file = 'libcassandra.' + builder.dylib_suffix
            path = os.path.join(builder.prefix_lib, lib_file)
            log_output(builder.log_prefix(self),
                       ['install_name_tool', '-id', '@rpath/' + lib_file, path])
