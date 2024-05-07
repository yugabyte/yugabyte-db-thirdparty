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
import subprocess
import tempfile
import time

from typing import Set, Optional

from yugabyte_db_thirdparty.custom_logging import log
from yugabyte_db_thirdparty.util import shlex_join, is_shared_library_name
from yugabyte_db_thirdparty import (
    ldd_util,
    file_util,
)
from yugabyte_db_thirdparty import download_manager
from yugabyte_db_thirdparty.download_manager import DownloadManager


ONEAPI_DEFAULT_BASE_DIR = '/opt/intel/oneapi'

DEFAULT_PACKAGE_TAG = 'v2024.1-1714789365'


def get_package_url_by_tag(tag: str) -> str:
    return f'https://github.com/yugabyte/yb-intel-oneapi-package/releases/download/' \
           f'{tag}/yb-intel-oneapi-{tag}.tar.gz'


class IntelOneAPIInstallation:
    version: str
    dirs_checked_for_existence: Set[str]

    # Base directory of the oneAPI installation. Either the default base directory, or a custom
    # directory for a YugabyteDB-packaged subset of oneAPI files.
    base_dir: str

    # We collect all the paths from the oneAPI installation actually used by our build process.
    # This is used for repackaging the useful subset of files into a smaller-size package.
    paths_to_be_packaged: Set[str]

    def __init__(self, base_dir: str, version: str) -> None:
        self.version = version
        self.dirs_checked_for_existence = set()
        self.base_dir = base_dir

        # Validate that certain directories exist.
        self.get_mkl_prefix()
        self.get_compiler_prefix()

        self.paths_to_be_packaged = set()

    def check_if_dir_exists(self, dir_path: str, must_be_prefix: bool = False) -> str:
        """
        An internal function to ensure that the given directory exists, returning the same
        directory. Only checks each directory once.

        :param must_be_prefix: if this is True, also checks that the given directory is a
            "prefix" directory, meaning it contains subdirectories such as "lib" and "include".
        """
        if dir_path not in self.dirs_checked_for_existence:
            if not os.path.exists(dir_path):
                raise IOError(f"Directory does not exist: {dir_path}")
            self.dirs_checked_for_existence.add(dir_path)

        if must_be_prefix:
            for subdir_name in ['lib']:
                self.check_if_dir_exists(os.path.join(dir_path, subdir_name), must_be_prefix=False)

        return dir_path

    def get_prefix_dir_for_component(self, component_name: str) -> str:
        dir_candidate = os.path.join(self.base_dir, component_name, self.version)
        return self.check_if_dir_exists(
            dir_candidate,
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

    def get_openmp_include_dir(self) -> str:
        """
        omp.h is found at the following paths in /opt/intel:

        /opt/intel/oneapi/2024.1/opt/compiler/include/omp.h (symlink)
        /opt/intel/oneapi/compiler/2024.1/opt/compiler/include/omp.h (the actual file)

        In a YugabyteDB-packaged Intel oneAPI subset archive, we install this and related headers
        into the corresponding directory at this relative path: compiler/2024.1/opt/compiler/include
        """
        return self.check_if_dir_exists(
            os.path.join(self.get_compiler_prefix(), 'opt', 'compiler', 'include'))

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

    def is_path_within_base_dir(self, absolute_path: str) -> bool:
        assert os.path.isabs(absolute_path), f'Expected an absolute path, got: {absolute_path}'
        return absolute_path.startswith(self.base_dir + '/')

    def add_path_to_be_packaged(self, path: str) -> None:
        assert not os.path.isabs(path)
        self.paths_to_be_packaged.add(path)

    def process_needed_libraries(self, dep_install_dir: str, dest_lib_dir: str) -> None:
        """
        Scans the given directory, which could be an installation directory of a third-party
        dependency, for executables and shared libraries that depend on shared libraries belonging
        to Intel oneAPI. For each shared library, also processes the corresponding static libraries
        and any .dbg files, if applicable.

        Has two modes of operation:
        - If we are packaging Intel oneAPI, only remembers the library paths to be packaged.
        - If we are not packging Intel oneAPI, copies the needed libraries to the specific
          destination directory (usually the library directory).
        """
        path_prefixes: Set[str] = set()
        for root, dirs, files in os.walk(dep_install_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                if ldd_util.should_use_ldd_on_file(file_path):
                    ldd_result = ldd_util.run_ldd(file_path)
                    if ldd_result.not_a_dynamic_executable():
                        continue
                    for full_path in list(ldd_result.resolved_dependencies):
                        if not self.is_path_within_base_dir(full_path):
                            continue
                        path_prefixes.add(ldd_util.remove_shared_lib_suffix(full_path))

        additional_path_prefixes: Set[str] = set()
        for path_prefix in path_prefixes:
            if os.path.basename(path_prefix) == 'libmkl_core':
                # Look for libmkl_def in the same directory. libmkl_def.so.2 is not directly
                # referenced by compiled executables but is needed during DiskANN CMake
                # configuration.
                additional_path_prefixes.add(path_prefix[:-4] + 'def')
        path_prefixes |= additional_path_prefixes

        file_names_found: Set[str] = set()
        for path_prefix in path_prefixes:
            for path_to_copy in glob.glob(path_prefix + '.*'):
                path_prefixes.add(path_prefix)
                self.add_path_to_be_packaged(
                    os.path.relpath(path_to_copy, self.base_dir))
                file_name = os.path.basename(path_to_copy)
                dest_path = os.path.join(dest_lib_dir, file_name)
                file_names_found.add(file_name)

                # When building an Intel oneAPI package, it is important NOT to copy
                # any libraries to the given directory (in practice, it is the
                # installed/common directory), because on a re-run this will cause
                # ldd to pick up the copied versions of these libraries and may result
                # in building a partial Intel oneAPI package insufficient for our needs.
                if (not is_package_build_mode_enabled() and
                        not os.path.exists(dest_path)):
                    file_util.copy_file_or_simple_symlink(path_to_copy, dest_path)

        mkl_def_library_found = False
        for file_name in file_names_found:
            if file_name.startswith('libmkl_def.'):
                mkl_def_library_found = True
        assert mkl_def_library_found, \
            "Did not find the libmkl_def library. Expected to find it in the same directory " \
            "as the libmkl_core library. File names to be packaged:\n    " + \
            "\n    ".join(sorted(file_names_found))

    def remember_paths_to_package_from_tag_dir(self, tag_dir: str) -> None:
        assert os.path.isabs(tag_dir)
        for root, dirs, files in os.walk(tag_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(file_path, tag_dir)
                self.add_path_to_be_packaged(rel_path)

    def create_package(self, dest_dir: str) -> None:
        tmp_dir = tempfile.mkdtemp(prefix='intel_oneapi_package_')
        try:
            self.do_create_package(tmp_dir, package_parent_dir=dest_dir)
        finally:
            pass
            shutil.rmtree(tmp_dir)

    def do_create_package(self, tmp_dir: str, package_parent_dir: str) -> None:
        """
        Package the files belonging to Intel oneAPI that we have identified as necessary for the
        build of our third-party dependencies. The archive will be created in the given directory.
        """
        if not os.path.isdir(package_parent_dir):
            raise IOError(
                f"The parent directory {package_parent_dir} for creating the Intel oneAPI "
                "package in does not exist")
        time_based_suffix = str(int(time.time()))
        package_name = f'yb-intel-oneapi-v{self.version}-{time_based_suffix}'
        package_dir = os.path.join(tmp_dir, package_name)
        os.mkdir(package_dir)
        log("Creating package in directory %s", package_dir)
        shared_libraries_found = False
        static_libraries_found = False
        for rel_path in sorted(self.paths_to_be_packaged):
            file_util.create_intermediate_dirs_for_rel_path(package_dir, rel_path)
            full_path = os.path.join(self.base_dir, rel_path)
            assert os.path.exists(full_path)
            dest_path = os.path.join(package_dir, rel_path)
            file_util.copy_file_or_simple_symlink(full_path, dest_path)
            if is_shared_library_name(rel_path):
                shared_libraries_found = True
            if rel_path.endswith('.a'):
                static_libraries_found = True
        archive_name = package_name + '.tar.gz'
        archive_path = os.path.join(package_parent_dir, archive_name)
        tar_cmd = ['tar', 'czf', archive_path, package_name]
        log("Creating Intel oneAPI subset archive at %s using command: %s",
            archive_path, shlex_join(tar_cmd))
        subprocess.check_call(tar_cmd, cwd=tmp_dir)
        if not shared_libraries_found or not static_libraries_found:
            raise ValueError(
                "Either static or shared libraries are missing from the packaged Intel oneAPI "
                "archive. This might happen because of a previous invocation of the build without "
                "--package-intel-oneapi, that resulted in installation of libraries such as "
                "libmkl_* and libiomp* into installed/common. Delete the installed directory "
                "and rerun the build. "
                f"shared_libraries_found={shared_libraries_found}, "
                f"static_libraries_found={static_libraries_found}"
            )


_oneapi_installation: Optional[IntelOneAPIInstallation] = None

_download_manager: Optional[DownloadManager] = None


def set_download_manager(download_manager: DownloadManager) -> None:
    global _download_manager
    _download_manager = download_manager


def download_intel_oneapi() -> IntelOneAPIInstallation:
    """
    Download Intel oneAPI containing only the necessary files from a YugabyteDB-hosted archive.
    Used during a normal yugabyte-db-thirdparty build.
    """
    url = get_package_url_by_tag(DEFAULT_PACKAGE_TAG)
    assert _download_manager is not None
    download_root = _download_manager.download_toolchain(url, '/opt/yb-build/intel-oneapi')
    return IntelOneAPIInstallation(version='2024.1', base_dir=download_root)


def find_complete_intel_oneapi_installation() -> IntelOneAPIInstallation:
    """
    Find a complete Intel oneAPI installation that was installed using the official installation
    procedure. Used during manual packaging of Intel oneAPI.
    """

    base_dir = ONEAPI_DEFAULT_BASE_DIR

    latest_compiler_symlink_path = os.path.join(base_dir, 'compiler', 'latest')
    if not os.path.exists(latest_compiler_symlink_path):
        raise IOError(f"Path does not exist: {latest_compiler_symlink_path}")
    if not os.path.islink(latest_compiler_symlink_path):
        raise IOError(f"Path is not a symlink: {latest_compiler_symlink_path}")
    oneapi_version = os.readlink(latest_compiler_symlink_path)
    assert '/' not in oneapi_version, \
        f"Expected the symlink {latest_compiler_symlink_path} to point to a directory named as " \
        f"the Intel oneAPI directory name but found: {oneapi_version}"
    return IntelOneAPIInstallation(version=oneapi_version, base_dir=base_dir)


def find_intel_oneapi() -> IntelOneAPIInstallation:
    global _oneapi_installation
    if _oneapi_installation is not None:
        return _oneapi_installation

    if is_package_build_mode_enabled():
        _oneapi_installation = find_complete_intel_oneapi_installation()
    else:
        _oneapi_installation = download_intel_oneapi()
    log(f"Using Intel oneAPI installation at {_oneapi_installation.base_dir}")
    return _oneapi_installation


_package_build_mode_enabled = False


def enable_package_build_mode(installed_common_dir: str) -> None:
    assert _oneapi_installation is None, \
        "Cannot enable Intel oneAPI package build mode once the oneAPI installation has been " \
        "selected."
    if not os.path.isdir(ONEAPI_DEFAULT_BASE_DIR):
        raise IOError(
            f"Intel oneAPI installation does not exist at {ONEAPI_DEFAULT_BASE_DIR}, "
            "cannot use it to create a package of an Intel oneAPI subset.")
    unexpected_files = []
    for pattern in ['libiomp*', 'libmkl_*']:
        for file_path in glob.glob(os.path.join(installed_common_dir, 'lib', pattern)):
            if os.path.exists(file_path):
                unexpected_files.append(file_path)
    if unexpected_files:
        raise ValueError(
            "Found Intel oneAPI libraries in the installed/common directory that will interfere "
            "with packaging all the necessary libraries when packging Intel oneAPI. Delete "
            "the installed directory and re-run the build from scratch with "
            "--package-intel-oneapi. Unexpected files:\n    "
            + '\n    '.join(sorted(unexpected_files)))

    global _package_build_mode_enabled
    _package_build_mode_enabled = True


def is_package_build_mode_enabled() -> bool:
    return _package_build_mode_enabled
