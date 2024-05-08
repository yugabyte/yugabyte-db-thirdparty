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
from yugabyte_db_thirdparty.intel_oneapi import find_intel_oneapi, IntelOneAPIInstallation
from yugabyte_db_thirdparty.rpath_util import get_rpath_flag
from yugabyte_db_thirdparty.env_helpers import EnvVarContext
from yugabyte_db_thirdparty.constants import (
    COMPILER_WRAPPER_ENV_VAR_NAME_TRACK_INCLUDES_IN_SUBDIRS_OF,
    COMPILER_WRAPPER_ENV_VAR_NAME_SAVE_USED_INCLUDE_TAGS_IN_DIR
)
from yugabyte_db_thirdparty import (
    util,
    intel_oneapi,
)


OPENMP_FLAG = '-fopenmp=libiomp5'


class DiskANNDependency(Dependency):
    oneapi_installation: Optional[IntelOneAPIInstallation]

    def __init__(self) -> None:
        super(DiskANNDependency, self).__init__(
            name='diskann',
            version='0.7.0-yb-4',
            url_pattern='https://github.com/yugabyte/diskann/archive/v{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = False
        self.oneapi_installation = None

    def configure_intel_oneapi(self) -> None:
        if self.oneapi_installation is not None:
            return

        self.oneapi_installation = find_intel_oneapi()

        # Original directory: /opt/intel/oneapi/mkl/2024.1/lib (3+ GB size)
        # YugabyteDB-packaged directory:
        # /opt/yb-build/intel-oneapi/yb-intel-oneapi-v2024.1-1714789365/mkl/2024.1/lib (621 MB)
        # Packaged libraries:
        #   - libmkl_core.a (402 MB, the largest by far)
        #   - libmkl_core.so
        #   - libmkl_core.so.2
        #   - libmkl_intel_ilp64.a
        #   - libmkl_intel_ilp64.so
        #   - libmkl_intel_ilp64.so.2
        #   - libmkl_intel_thread.a
        #   - libmkl_intel_thread.so
        #   - libmkl_intel_thread.so.2
        self.intel_mkl_lib_dir = self.oneapi_installation.get_mkl_lib_dir()
        log("intel_mkl_lib_dir: %s", self.intel_mkl_lib_dir)

        # Original directory:
        # /opt/intel/oneapi/mkl/2024.1/include (22 MB size)
        #
        # YugabyteDB-packaged directory:
        # /opt/yb-build/intel-oneapi/yb-intel-oneapi-v2024.1-1714789365/mkl/2024.1/include (6 MB)
        self.intel_mkl_include_dir = self.oneapi_installation.get_mkl_include_dir()
        log("intel_mkl_include_dir: %s", self.intel_mkl_include_dir)

        # Original directory: /opt/intel/oneapi/compiler/2024.1/lib (1 GB+ size)
        #
        # YugabyteDB-packaged directory:
        # /opt/yb-build/intel-oneapi/yb-intel-oneapi-v2024.1-1714789365/compiler/2024.1/lib
        #
        # In the YugabyteDB-packaged archive, this directory contains libraries:
        # libiomp5.a  libiomp5.dbg  libiomp5.so
        # (13 MB size)
        self.openmp_lib_dir = self.oneapi_installation.get_openmp_lib_dir()
        log("openmp_lib_dir: %s", self.openmp_lib_dir)

        # Original directory: /opt/intel/oneapi/compiler/2024.1/opt/compiler/include
        # Possible path inside YugabyteDB-packaged Intel oneAPI directory:
        # /opt/yb-build/intel-oneapi/yb-intel-oneapi-v2024.1-1714789365/compiler/2024.1/opt/compiler/include
        self.openmp_include_dir = self.oneapi_installation.get_openmp_include_dir()
        log("openmp_include_dir: %s", self.openmp_include_dir)

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        self.configure_intel_oneapi()
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
        self.configure_intel_oneapi()
        rpaths = [
            # This directory must be listed first so that the libraries copied to the
            # installed/common/lib/intel-oneapi would be preferred.
            self.get_intel_oneapi_installed_lib_dir(builder)
        ] + self.get_intel_oneapi_lib_dirs() + [
            # This is the directory that will contain the installed libdiskann.so library.
            get_rpath_flag(os.path.join(self.get_install_prefix(builder), 'lib')),
        ]

        return [
            # We need to link with the libaio library. It is surprising that DiskANN's
            # CMakeLists.txt itself does not specify this dependency.
            '-laio',
        ] + [get_rpath_flag(p) for p in rpaths]

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

    def get_intel_oneapi_installed_lib_dir(self, builder: BuilderInterface) -> str:
        return os.path.join(builder.fs_layout.tp_installed_common_dir, 'lib', 'intel-oneapi')

    def get_intel_oneapi_lib_dirs(self) -> List[str]:
        return [self.openmp_lib_dir, self.intel_mkl_lib_dir]

    def build(self, builder: BuilderInterface) -> None:
        self.configure_intel_oneapi()
        assert self.oneapi_installation is not None

        install_prefix = self.get_install_prefix(builder)

        # We must use the dictionary syntax of EnvVarContext constructor below, because the
        # environment variable name is specified as an expression (constant).
        env_vars = {}
        used_include_tags_dir: Optional[str] = None
        if intel_oneapi.is_package_build_mode_enabled():
            used_include_tags_dir = util.create_preferably_in_mem_tmp_dir(
                prefix='used_include_tags_',
                suffix='_' + util.get_temporal_randomized_file_name_suffix(),
                delete_at_exit=True)
            env_vars[COMPILER_WRAPPER_ENV_VAR_NAME_TRACK_INCLUDES_IN_SUBDIRS_OF] = \
                intel_oneapi.ONEAPI_DEFAULT_BASE_DIR
            env_vars[COMPILER_WRAPPER_ENV_VAR_NAME_SAVE_USED_INCLUDE_TAGS_IN_DIR] = \
                used_include_tags_dir

        with EnvVarContext(env_vars):
            builder.build_with_cmake(
                self,
                extra_cmake_args=[
                    '-DCMAKE_BUILD_TYPE=Release',
                    # Still search for libraries in the default prefix path, but install DiskANN
                    # into a custom subdirectory of it.
                    '-DCMAKE_SYSTEM_PREFIX_PATH=' + builder.prefix,
                    '-DOMP_PATH=' + self.openmp_lib_dir,
                    # To avoid this message during CMake configuration:
                    # Could not find Intel MKL in standard locations; use -DMKL_PATH to specify
                    f'-DMKL_PATH={self.intel_mkl_lib_dir}',
                    f'-DMKL_INCLUDE_PATH={self.intel_mkl_include_dir}',
                ]
            )

        builder.copy_include_files(
            dep=self,
            rel_src_include_path='include',
            dest_include_path=os.path.join(install_prefix, 'include'))

        lib_dest_dir = self.get_intel_oneapi_installed_lib_dir(builder)

        self.oneapi_installation.process_needed_libraries(
            install_prefix, lib_dest_dir, rpaths_for_ldd=self.get_intel_oneapi_lib_dirs())
        if used_include_tags_dir is not None:
            self.oneapi_installation.remember_paths_to_package_from_tag_dir(used_include_tags_dir)
