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

import os
from sys_detection import is_linux

from build_definitions import ExtraDownload, VALID_BUILD_GROUPS
from yugabyte_db_thirdparty.archive_handling import make_archive_name

from typing import Optional, List, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .builder_interface import BuilderInterface


class Dependency:
    download_url: Optional[str]
    extra_downloads: List[ExtraDownload]
    patches: List[str]
    patch_strip: Optional[int]
    post_patch: List[str]
    copy_sources: bool
    license: Optional[str]
    mkdir_only: bool
    archive_name: Optional[str]

    # Enforce the use of lld linker on Clang 14 and later by appending it to the linker flags in
    # the compiler wrapper.
    enforce_lld_in_compiler_wrapper: bool

    def __init__(
            self,
            name: str,
            version: str,
            url_pattern: Optional[str],
            build_group: str,
            archive_name_prefix: Optional[str] = None,
            license: Optional[str] = None,
            mkdir_only: bool = False) -> None:
        self.name = name
        self.version = version
        self.dir_name = '{}-{}'.format(name, version)
        self.underscored_version = version.replace('.', '_')
        if url_pattern is not None:
            self.download_url = url_pattern.format(version, self.underscored_version)
        else:
            self.download_url = None
        self.build_group = build_group

        self.archive_name = None
        self.mkdir_only = mkdir_only
        if not mkdir_only:
            self.archive_name = make_archive_name(
                archive_name_prefix or name, version, self.download_url)

        self.patch_version = 0
        self.extra_downloads = []
        self.patches = []

        # In most cases, we need to apply patches with a -p1 argument. This is the case for patches
        # generated by "git diff" and "git show". In other cases, subclasses can set patch_strip
        # to a different value.
        self.patch_strip = 1

        self.post_patch = []
        self.copy_sources = False
        self.license = license

        if build_group not in VALID_BUILD_GROUPS:
            raise ValueError("Invalid build group: %s, should be one of: %s" % (
                build_group, VALID_BUILD_GROUPS))

    def get_additional_compiler_flags(
            self,
            builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_c_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_cxx_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_ld_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_compiler_wrapper_ld_flags_to_append(self,  builder: 'BuilderInterface') -> List[str]:
        """
        In some cases, we need to use the compiler_wrapper to add ld flags at the very end of the
        compiler wrapper command line.
        """
        llvm_major_version: Optional[int] = builder.compiler_choice.get_llvm_major_version()
        use_lld_flag = '-fuse-ld=lld'
        if (is_linux and
                llvm_major_version is not None and
                llvm_major_version >= 12 and
                builder.lto_type is not None and
                use_lld_flag in builder.ld_flags):
            return [use_lld_flag]

        return []

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: 'BuilderInterface') -> Set[str]:
        """
        In some cases, we need to use the compiler_wrapper to remove linker flags.
        """
        return set()

    def get_additional_assembler_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_cmake_args(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def should_build(self, builder: 'BuilderInterface') -> bool:
        return True

    def postprocess_ninja_build_file(
            self,
            builder: 'BuilderInterface',
            ninja_build_file_path: str) -> None:
        """
        Allows some dependencies to post-process the build.ninja file generated by CMake.
        """
        if not os.path.exists(ninja_build_file_path):
            raise IOError("File does not exist: %s",
                          os.path.abspath(ninja_build_file_path))

    def build(self, builder: 'BuilderInterface') -> None:
        raise NotImplementedError()

    def get_install_prefix(self, builder: 'BuilderInterface') -> str:
        return builder.prefix

    def get_archive_name(self) -> Optional[str]:
        return self.archive_name

    def get_source_dir_basename(self) -> str:
        return self.dir_name

    def need_compiler_wrapper(self, builder: 'BuilderInterface') -> bool:
        return (bool(self.get_compiler_wrapper_ld_flags_to_append(builder)) or
                bool(self.get_compiler_wrapper_ld_flags_to_remove(builder)))
