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

from build_definitions import ExtraDownload, make_archive_name, VALID_BUILD_GROUPS

from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .builder_interface import BuilderInterface


class Dependency:
    download_url: Optional[str]
    extra_downloads: List[ExtraDownload]
    patches: List[str]
    patch_strip: Optional[int]
    post_patch: List[str]
    copy_sources: bool

    def __init__(
            self,
            name: str,
            version: str,
            url_pattern: Optional[str],
            build_group: str) -> None:
        self.name = name
        self.version = version
        self.dir_name = '{}-{}'.format(name, version)
        self.underscored_version = version.replace('.', '_')
        if url_pattern is not None:
            self.download_url = url_pattern.format(version, self.underscored_version)
        else:
            self.download_url = None
        self.build_group = build_group
        self.archive_name = make_archive_name(name, version, self.download_url)
        self.patch_version = 0
        self.extra_downloads = []
        self.patches = []
        self.patch_strip = None
        self.post_patch = []
        self.copy_sources = False

        if build_group not in VALID_BUILD_GROUPS:
            raise ValueError("Invalid build group: %s, should be one of: %s" % (
                build_group, VALID_BUILD_GROUPS))

    def get_additional_c_cxx_flags(
            self,
            builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_c_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_cxx_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_excluded_c_cxx_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_excluded_ld_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_excluded_libs(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def should_build(self, builder: 'BuilderInterface') -> bool:
        return True

    def build(self, builder: 'BuilderInterface') -> None:
        raise NotImplementedError()
