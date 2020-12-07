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

from yugabyte_db_thirdparty.util import YB_THIRDPARTY_DIR
from yugabyte_db_thirdparty.dependency import Dependency
from yugabyte_db_thirdparty.custom_logging import heading, log
from yugabyte_db_thirdparty.util import remove_path
from build_definitions import BUILD_TYPES, BUILD_TYPE_COMMON

import os
from typing import Optional, List


class FileSystemLayout:
    tp_build_dir: str
    tp_download_dir: str
    tp_src_dir: str
    tp_installed_dir: str

    def __init__(self) -> None:
        self.tp_build_dir = os.path.join(YB_THIRDPARTY_DIR, 'build')
        self.tp_src_dir = os.path.join(YB_THIRDPARTY_DIR, 'src')
        self.tp_download_dir = os.path.join(YB_THIRDPARTY_DIR, 'download')
        self.tp_installed_dir = os.path.join(YB_THIRDPARTY_DIR, 'installed')
        self.tp_installed_common_dir = os.path.join(self.tp_installed_dir, BUILD_TYPE_COMMON)
        self.tp_installed_llvm7_common_dir = os.path.join(
                self.tp_installed_dir + '_llvm7', BUILD_TYPE_COMMON)

    def get_archive_path(self, dep: Dependency) -> Optional[str]:
        archive_name = dep.get_archive_name()
        if archive_name is None:
            return None
        return os.path.join(self.tp_download_dir, archive_name)

    def get_source_path(self, dep: Dependency) -> str:
        return os.path.join(self.tp_src_dir, dep.get_source_dir_basename())

    def clean(self, selected_dependencies: List[Dependency]) -> None:
        """
        TODO: deduplicate this vs. the clean_thirdparty.sh script. Possibly even remove the
        clean_thirdparty.sh script.
        """
        heading('Clean')
        for dependency in selected_dependencies:
            for dir_name in BUILD_TYPES:
                for leaf in [dependency.name, '.build-stamp-{}'.format(dependency)]:
                    path = os.path.join(self.tp_build_dir, dir_name, leaf)
                    if os.path.exists(path):
                        log("Removing %s build output: %s", dependency.name, path)
                        remove_path(path)
            if dependency.dir_name is not None:
                src_dir = self.get_source_path(dependency)
                if os.path.exists(src_dir):
                    log("Removing %s source: %s", dependency.name, src_dir)
                    remove_path(src_dir)

            archive_path = self.get_archive_path(dependency)
            if archive_path is not None:
                log("Removing %s archive: %s", dependency.name, archive_path)
                remove_path(archive_path)

    def get_build_stamp_path_for_dependency(self, dep: Dependency, build_type: str) -> str:
        return os.path.join(
            self.tp_build_dir, build_type, '.build-stamp-{}'.format(dep.name))
