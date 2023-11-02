# Copyright (c) Yugabyte, Inc.
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
import logging

from typing import Optional, List, Dict, Tuple
from enum import Enum

from yugabyte_db_thirdparty.util import YB_THIRDPARTY_DIR, remove_path
from yugabyte_db_thirdparty.dependency import Dependency
from yugabyte_db_thirdparty.custom_logging import heading, log
from yugabyte_db_thirdparty.compiler_choice import CompilerChoice
from yugabyte_db_thirdparty.linuxbrew import using_linuxbrew
from yugabyte_db_thirdparty.arch import get_target_arch

from build_definitions import BuildType


class SourcePathType(Enum):
    DEFAULT = 'DEFAULT'
    DEV_REPO = 'DEV_REPO'


class FileSystemLayout:
    tp_build_dir: str
    tp_src_dir: str
    tp_download_dir: str
    tp_installed_dir: str
    tp_installed_common_dir: str

    build_specific_subdir: str

    # Maps dependency names to their custom source directories used for development.
    dev_repo_mappings: Dict[str, str]

    def __init__(self) -> None:
        self.tp_src_dir = os.path.join(YB_THIRDPARTY_DIR, 'src')
        self.tp_download_dir = os.path.join(YB_THIRDPARTY_DIR, 'download')
        self.dev_repo_mappings = {}

    def finish_initialization(
            self,
            per_build_subdirs: Optional[bool],
            compiler_choice: CompilerChoice,
            lto_type: Optional[str]) -> None:
        """
        :param per_build_subdirs: whether to create a separate build directory for each build type,
            or if this is None, the value is determined automatically based on the contents of the
            build directory.
        """
        build_parent_dir = self.tp_build_dir = os.path.join(YB_THIRDPARTY_DIR, 'build')
        installed_parent_dir = os.path.join(YB_THIRDPARTY_DIR, 'installed')
        if (per_build_subdirs is None and
                os.path.exists(build_parent_dir) and
                os.path.isdir(build_parent_dir)):
            for dir_name in os.listdir(build_parent_dir):
                if dir_name != 'llvm-tools' and '-' in dir_name:
                    logging.info(
                        "Found directory named %s in %s, assuming per-build subdirs. "
                        "To disable this behavior, specify --no-per-build-subdirs.",
                        dir_name, build_parent_dir)
                    per_build_subdirs = True
                    break

        if per_build_subdirs:
            build_specific_subdir = '-'.join(compiler_choice.get_build_type_components(
                lto_type=lto_type, with_arch=True))
            self.tp_build_dir = os.path.join(build_parent_dir, build_specific_subdir)
            self.tp_installed_dir = os.path.join(installed_parent_dir, build_specific_subdir)
        else:
            self.tp_build_dir = build_parent_dir
            self.tp_installed_dir = installed_parent_dir

        self.tp_installed_common_dir = os.path.join(
            self.tp_installed_dir, BuildType.COMMON.dir_name())

    def get_archive_path(self, dep: Dependency) -> Optional[str]:
        archive_name = dep.get_archive_name()
        if archive_name is None:
            return None
        return os.path.join(self.tp_download_dir, archive_name)

    def get_source_path(self, dep: Dependency) -> str:
        return self.get_source_path_with_type(dep)[0]

    def get_source_path_with_type(self, dep: Dependency) -> Tuple[str, SourcePathType]:
        if dep.name in self.dev_repo_mappings:
            return self.dev_repo_mappings[dep.name], SourcePathType.DEV_REPO

        return os.path.join(self.tp_src_dir, dep.get_source_dir_basename()), SourcePathType.DEFAULT

    def remove_path_for_dependency(
            self, dep: Dependency, path: Optional[str], description: str) -> None:
        full_description = f"{description} for dependency {dep.name}"
        if path is None:
            log(f"Path to {full_description} is not defined")
            return
        if os.path.exists(path):
            log(f"Removing {full_description} at {path}")
            remove_path(path)
        else:
            log(f"Could not find {full_description} at {path}, nothing to remove")

    def clean(
            self,
            selected_dependencies: List[Dependency],
            clean_downloads: bool) -> None:
        """
        TODO: deduplicate this vs. the clean_thirdparty.sh script. Possibly even remove the
        clean_thirdparty.sh script.
        """
        heading('Clean')

        for dependency in selected_dependencies:
            for build_type in BuildType:
                self.remove_path_for_dependency(
                    dep=dependency,
                    path=self.get_build_stamp_path_for_dependency(dependency, build_type),
                    description="build stamp")
                self.remove_path_for_dependency(
                    dep=dependency,
                    path=self.get_build_dir_for_dependency(dependency, build_type),
                    description="build stamp")

                if dependency.dir_name is not None:
                    self.remove_path_for_dependency(
                        dep=dependency,
                        path=self.get_source_path(dependency),
                        description="source")

            if clean_downloads:
                self.remove_path_for_dependency(
                    dep=dependency,
                    path=self.get_archive_path(dependency),
                    description="downloaded archive")

    def get_build_stamp_path_for_dependency(self, dep: Dependency, build_type: BuildType) -> str:
        return os.path.join(self.tp_build_dir,
                            build_type.dir_name(),
                            '.build-stamp-{}'.format(dep.name))

    def get_build_dir_for_dependency(self, dep: Dependency, build_type: BuildType) -> str:
        return os.path.join(self.tp_build_dir, build_type.dir_name(), dep.dir_name)

    def get_llvm_tool_dir(self) -> str:
        """
        Returns a directory name where we will put various tools with standard names, such as nm,
        ar, ld, as symlinks to their LLVM counterparts.
        """
        return os.path.join(self.tp_build_dir, 'llvm-tools')

    def add_dev_repo_mapping(self, mapping_str: str) -> None:
        components = mapping_str.split('=', 1)
        if len(components) != 2:
            raise ValueError(
                f"Expected a dev repo mapping to be of the form name=directory, got: {mapping_str}")
        dep_name, repo_dir = components
        repo_dir = os.path.expanduser(repo_dir)
        if dep_name in self.dev_repo_mappings:
            raise ValueError(
                f"Duplicate development repository directory mapping for dependency {dep_name}: "
                f"{self.dev_repo_mappings[dep_name]} and {repo_dir}")
        self.dev_repo_mappings[dep_name] = repo_dir
