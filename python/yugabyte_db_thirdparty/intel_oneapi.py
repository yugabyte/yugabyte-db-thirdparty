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

"""
Utilities for finding and using an Intel OneAPI installation. Because Intel OneAPI takes a lot of
disk space, we copy only the necesary files from it to the thirdparty installed directory.
"""

import glob
import os
import shutil

from typing import Set, Optional

from yugabyte_db_thirdparty import ldd_util
from yugabyte_db_thirdparty.custom_logging import log


ONEAPI_BASE_DIR = '/opt/intel/oneapi'


class IntelOneAPIInstallation:
    version: str
    checked_dirs: Set[str]

    def __init__(self, version: str) -> None:
        self.version = version
        self.checked_dirs = set()

        # Validate that certain directories exist.
        self.get_mkl_prefix()
        self.get_compiler_prefix()

    def check_if_dir_exists(self, dir_path: str, must_be_prefix: bool = False) -> str:
        """
        An internal function to ensure that the given directory exists, returning the same
        directory. Only checks each directory once.

        :param must_be_prefix: if this is True, also checks that the given directory is a
            "prefix" directory, meaning it contains subdirectories such as "lib" and "include".
        """
        if dir_path not in self.checked_dirs:
            if not os.path.exists(dir_path):
                raise IOError(f"Directory does not exist: {dir_path}")
            self.checked_dirs.add(dir_path)

        if must_be_prefix:
            for subdir_name in ['lib', 'include']:
                self.check_if_dir_exists(os.path.join(dir_path, subdir_name), must_be_prefix=False)

        return dir_path

    def get_prefix_dir_for_component(self, component_name: str) -> str:
        return self.check_if_dir_exists(
            os.path.join(ONEAPI_BASE_DIR, component_name, self.version),
            must_be_prefix=True)

    def get_mkl_prefix(self) -> str:
        """
        Returns the prefix directory for Intel MKL (Math Kernel Library).
        Example return value: /opt/intel/oneapi/mkl/2024.1
        This directory typically contains the following subdirectories:
        bin  env  etc  include  lib  lib32  share
        """
        return self.get_prefix_dir_for_component('mkl')

    def get_mkl_lib_dir(self) -> str:
        return os.path.join(self.get_mkl_prefix(), 'lib')

    def get_mkl_include_dir(self) -> str:
        return os.path.join(self.get_mkl_prefix(), 'include')

    def get_compiler_prefix(self) -> str:
        """
        Returns the prefix directory for Intel Compiler and runtime (needed for OpenMP libraries).
        Example return value: /opt/intel/oneapi/compiler/2024.1
        This directory typically contains the following subdirectories:
        bin  bin32  env  etc  include  lib  lib32  opt  share
        """
        return self.get_prefix_dir_for_component('compiler')

    def get_compiler_include_dir(self) -> str:
        return os.path.join(self.get_compiler_prefix(), 'include')

    def get_openmp_include_dir(self) -> str:
        return self.check_if_dir_exists(
            os.path.join(self.get_compiler_prefix(), 'opt/compiler/include'))

    def get_openmp_lib_dir(self) -> str:
        """
        Returns the directory where the OpenMP library, libiomp5, is located.
        Example return value: /opt/intel/oneapi/compiler/2024.1/lib
        Example of OpenMP library paths found there:
            /opt/intel/oneapi/compiler/2024.1/lib/libiomp5.a
            /opt/intel/oneapi/compiler/2024.1/lib/libiomp5.dbg
            /opt/intel/oneapi/compiler/2024.1/lib/libiomp5_db.so
            /opt/intel/oneapi/compiler/2024.1/lib/libiomp5.so
        """
        return self.check_if_dir_exists(os.path.join(self.get_compiler_prefix(), 'lib'))

    def copy_needed_libraries(self, dep_install_dir: str, dest_lib_dir: str) -> None:
        """
        Scans the given directory, which could be an installation directory of a third-party
        dependency, for executables and shared libraries that depend on shared libraries belonging
        to Intel oneAPI. Copies the needed libraries, including the corresponding static libraries
        and symlinks, to the specified destination directory.
        """
        for root, dirs, files in os.walk(dep_install_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                if ldd_util.should_use_ldd_on_file(file_path):
                    ldd_result = ldd_util.run_ldd(file_path)
                    if ldd_result.not_a_dynamic_executable():
                        continue
                    for full_path in list(ldd_result.resolved_dependencies):
                        if not full_path.startswith(ONEAPI_BASE_DIR + '/'):
                            continue
                        path_prefix = ldd_util.remove_shared_lib_suffix(full_path)
                        for lib_path in glob.glob(path_prefix + '.*'):
                            dest_path = os.path.join(dest_lib_dir, os.path.basename(lib_path))
                            if not os.path.exists(dest_path):
                                if os.path.islink(lib_path):
                                    link_target = os.readlink(lib_path)
                                    assert '/' not in link_target, \
                                        f"Expected symlink target {link_target} of {lib_path} " \
                                        f"to be a file name only."
                                    log(f"Symlinking {dest_path} -> {link_target}")
                                    os.symlink(link_target, dest_path)
                                else:
                                    log(f"Copying {lib_path} to {dest_path}")
                                    shutil.copy(lib_path, dest_path)


oneapi_installation: Optional[IntelOneAPIInstallation] = None


def find_intel_oneapi() -> IntelOneAPIInstallation:
    global oneapi_installation
    if oneapi_installation is not None:
        return oneapi_installation

    latest_compiler_symlink_path = '/opt/intel/oneapi/compiler/latest'
    if not os.path.exists(latest_compiler_symlink_path):
        raise IOError(f"Path does not exist: {latest_compiler_symlink_path}")
    if not os.path.islink(latest_compiler_symlink_path):
        raise IOError(f"Path is not a symlink: {latest_compiler_symlink_path}")
    oneapi_version = os.readlink(latest_compiler_symlink_path)
    assert '/' not in oneapi_version, \
        f"Expected the symlink {latest_compiler_symlink_path} to point to a directory named as " \
        f"the Intel oneAPI directory name but found: {oneapi_version}"
    oneapi_installation = IntelOneAPIInstallation(oneapi_version)
    return oneapi_installation
