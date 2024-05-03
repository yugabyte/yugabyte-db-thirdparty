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
from typing import Optional, List, Set, TYPE_CHECKING

from sys_detection import is_linux, is_macos

from build_definitions import ExtraDownload, BuildGroup
from yugabyte_db_thirdparty.archive_handling import make_archive_name
from yugabyte_db_thirdparty.git_util import parse_github_url
from yugabyte_db_thirdparty.custom_logging import log

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
    local_archive: Optional[str]

    # For dependencies built with configure/autotools, where out-of-source build is not possible,
    # this tells the initial step to create separate build directories for shared and static builds.
    shared_and_static: bool

    # For Bazel dependencies, this is the name of the subdirectory in Bazel's build directory
    # that is mapped to this project's build directory. Used during rewriting the compilation
    # database.
    bazel_project_subdir_name: Optional[str]

    github_org_name: Optional[str]
    github_repo_name: Optional[str]
    github_ref: Optional[str]

    def __init__(
            self,
            name: str,
            version: str,
            url_pattern: Optional[str],
            build_group: BuildGroup,
            archive_name_prefix: Optional[str] = None,
            license: Optional[str] = None,
            mkdir_only: bool = False,
            local_archive: Optional[str] = None) -> None:
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
        self.local_archive = local_archive

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

        self.shared_and_static = False
        self.bazel_project_subdir_name = None

        if self.download_url is not None:
            parse_result = parse_github_url(self.download_url)
            self.github_org_name = None
            self.github_repo_name = None
            self.github_ref = None
            if parse_result:
                self.github_org_name, self.github_repo_name, self.github_ref = parse_result
            elif self.download_url.startswith('https://github.com/'):
                log("Warning: failed to parse GitHub URL %s", self.download_url)

    def get_additional_compiler_flags(
            self,
            builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_c_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_cxx_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_additional_leading_ld_flags(self, builder: 'BuilderInterface') -> List[str]:
        """
        These flags are added in front of the linker command line.
        """
        return []

    def get_additional_ld_flags(self, builder: 'BuilderInterface') -> List[str]:
        return []

    def get_compiler_wrapper_ld_flags_to_append(self,  builder: 'BuilderInterface') -> List[str]:
        """
        In some cases, we need to use the compiler_wrapper to add ld flags at the very end of the
        compiler wrapper command line.
        """
        llvm_major_version: Optional[int] = builder.compiler_choice.get_llvm_major_version()
        if (is_linux() and
                llvm_major_version is not None and
                llvm_major_version >= 12 and
                builder.lto_type is not None):
            return ['-fuse-ld=lld']

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

    def use_cppflags_env_var(self) -> bool:
        '''
        Some dependencies expect us to specify include directories in the CPPFLAGS (C preprocessor
        flags) environment variable. Others do not use this variable and we need to put include
        directories in CFLAGS and CXXFLAGS.

        This function only affects dependencies built with configure (autotools), not with CMake.
        '''
        return False
