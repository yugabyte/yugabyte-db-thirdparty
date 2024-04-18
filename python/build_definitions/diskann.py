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


INTEL_ONEAPI_COMPILER_DIR = '/opt/intel/oneapi/2024.1/opt/compiler'
INTEL_ONEAPI_RUNTIME_DIR = '/opt/intel/oneapi/2024.1'


class DiskANNDependency(Dependency):
    def __init__(self) -> None:
        super(DiskANNDependency, self).__init__(
            name='diskann',
            version='0.7.0-yb-2',
            url_pattern='https://github.com/yugabyte/diskann/archive/v{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = False

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        return [
            f"-I{os.path.join(INTEL_ONEAPI_COMPILER_DIR, 'include')}",
            f"-I{os.path.join(INTEL_ONEAPI_RUNTIME_DIR, 'include')}",
            # TODO: ideally, the -L flags below should be linker flags. However, FindOpenMP
            # does not correctly pass them to the linker command line in that case.
            f"-L{os.path.join(INTEL_ONEAPI_COMPILER_DIR, 'lib')}",
            f"-L{os.path.join(INTEL_ONEAPI_RUNTIME_DIR, 'lib')}",
            "-fopenmp=libiomp5"
        ]

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        return [
            # We need to link with the libaio library. It is surprising that DiskANN's
            # CMakeLists.txt does not specify this dependency.
            '-laio',
            # TODO: specify this rpath automatically.
            '-Wl,-rpath=/opt/intel/oneapi/mkl/2024.1/lib',
            '-Wl,-rpath=/opt/intel/oneapi/compiler/2024.1/lib',
        ]

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: BuilderInterface) -> Set[str]:
        """
        TODO: is there a better way to prevent FindOpenMP from using -fopenmp=libomp while also
        using -fopenmp=libiomp5, when checking for OpenMP installation path?
        """
        return {"-fopenmp=libomp"}

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(
            self,
            extra_args=[
                '-DCMAKE_BUILD_TYPE=Release',
                '-DBUILD_SHARED_LIBS=ON',
                '-DOMP_PATH=/opt/intel/oneapi/compiler/2024.1/lib',
                '-DOpenMP_CXX_FLAGS=-fopenmp=libiomp5',
                '-DOpenMP_C_FLAGS=-fopenmp=libiomp5',
                # DiskANN tries to search the following paths by default:
                # "/opt/intel/oneapi/compiler/latest/linux/compiler/lib/intel64_lin/libiomp5.so;/usr/lib/x86_64-linux-gnu/libiomp5.so;/opt/intel/lib/intel64_lin/libiomp5.so
                # TODO: automatically find the right directory within /opt/intel/oneapi
                # TODO: check if we are given a compatible version of oneapi
            ]
        )
