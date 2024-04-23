#
# Copyright (c) YugabyteDB, Inc.
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
from typing import List

from yugabyte_db_thirdparty.build_definition_helpers import *
from yugabyte_db_thirdparty.builder_interface import BuilderInterface  # noqa
from yugabyte_db_thirdparty.intel_oneapi import find_intel_oneapi
from yugabyte_db_thirdparty.rpath_util import get_rpath_flag


INTEL_ONEAPI_COMPILER_DIR = '/opt/intel/oneapi/2024.1/opt/compiler'
INTEL_ONEAPI_RUNTIME_DIR = '/opt/intel/oneapi/2024.1'

OPENMP_FLAG = '-fopenmp=libiomp5'


class DiskANNDependency(Dependency):
    def __init__(self) -> None:
        super(DiskANNDependency, self).__init__(
            name='diskann',
            version='0.7.0-yb-4',
            url_pattern='https://github.com/yugabyte/diskann/archive/v{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = False
        self.oneapi_installation = find_intel_oneapi()

        self.intel_mkl_lib_dir = self.oneapi_installation.get_mkl_lib_dir()
        self.intel_mkl_include_dir = self.oneapi_installation.get_mkl_include_dir()
        self.openmp_lib_dir = self.oneapi_installation.get_openmp_lib_dir()
        self.openmp_include_dir = self.oneapi_installation.get_openmp_include_dir()

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        return [
            "-I" + self.openmp_include_dir,
            "-I" + self.intel_mkl_include_dir,
            # TODO: ideally, the -L flags below should be linker flags. However, the FindOpenMP
            # CMake module does not correctly pass them to the linker command line in that case.
            "-L" + self.openmp_lib_dir,
            "-L" + self.intel_mkl_lib_dir,
            OPENMP_FLAG
        ]

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        return [
            # We need to link with the libaio library. It is surprising that DiskANN's
            # CMakeLists.txt itself does not specify this dependency.
            '-laio',
            # TODO: specify this rpath automatically.
            get_rpath_flag(self.openmp_lib_dir),
            get_rpath_flag(self.intel_mkl_lib_dir),
        ]

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: BuilderInterface) -> Set[str]:
        """
        TODO: is there a better way to prevent FindOpenMP from using -fopenmp=libomp while also
        using -fopenmp=libiomp5, when checking for OpenMP installation path?
        """
        return {"-fopenmp=libomp"}

    def get_install_prefix(self, builder: BuilderInterface) -> str:
        """
        We install DiskANN into a non-standard directory because it comes with a large number of
        tools that we don't want to mix with the rest of the contents of the installed/.../bin
        directories.
        """
        return os.path.join(builder.prefix, 'diskann')

    def build(self, builder: BuilderInterface) -> None:
        install_prefix = self.get_install_prefix(builder)
        builder.build_with_cmake(
            self,
            extra_cmake_args=[
                '-DCMAKE_BUILD_TYPE=Release',
                # Still search for libraries in the default prefix path, but install DiskANN into
                # a custom subdirectory of it.
                '-DCMAKE_SYSTEM_PREFIX_PATH=' + builder.prefix,
                '-DOMP_PATH=' + self.openmp_lib_dir,
            ]
        )
        builder.copy_include_files(
            dep=self,
            rel_src_include_path='include',
            dest_include_path=os.path.join(install_prefix, 'include'))

        installed_common_lib_dir = os.path.join(builder.fs_layout.tp_installed_common_dir, 'lib')
        self.oneapi_installation.copy_needed_libraries(install_prefix, installed_common_lib_dir)
