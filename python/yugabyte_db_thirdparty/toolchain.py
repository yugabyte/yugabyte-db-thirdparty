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
import re
from llvm_installer import LlvmInstaller

from yugabyte_db_thirdparty.download_manager import DownloadManager
from yugabyte_db_thirdparty.util import YB_THIRDPARTY_DIR, write_file

from typing import Optional, List, Optional

import sys_detection
from sys_detection import SHORT_OS_NAME_REGEX_STR, is_compatible_os_and_version


LINUXBREW_URL = (
    'https://github.com/yugabyte/brew-build/releases/download/'
    '20181203T161736v9/linuxbrew-20181203T161736v9.tar.gz'
)

LLVM_VERSION_FROM_ARCHIVE_NAME_RE = re.compile(
        rf'^yb-llvm-v(.*)-[0-9]+-[0-9a-f]+-.*')


def get_llvm_url(tag: str) -> str:
    return 'https://github.com/yugabyte/build-clang/releases/download/%s/yb-llvm-%s.tar.gz' % (
            tag, tag)


LLVM_VERSIONS = [11, 12, 13, 14]

TOOLCHAIN_TYPES = (
    ['llvm%d' % v for v in LLVM_VERSIONS] +
    ['linuxbrew'] +
    ['llvm%d_linuxbrew' % v for v in LLVM_VERSIONS]
)


class Toolchain:
    toolchain_url: str
    toolchain_type: str
    toolchain_root: str
    compiler_type: Optional[str]

    def __init__(
            self,
            toolchain_url: str,
            toolchain_type: str,
            toolchain_root: str) -> None:
        self.toolchain_url = toolchain_url
        self.toolchain_type = toolchain_type
        self.toolchain_root = toolchain_root
        self.compiler_type = None

    def get_compiler_type(self) -> str:
        if self.compiler_type:
            return self.compiler_type

        candidate_paths = []
        for compiler_type_candidate in ['clang', 'gcc']:
            compiler_path = os.path.join(self.toolchain_root, 'bin', compiler_type_candidate)
            if os.path.exists(compiler_path):
                self.compiler_type = compiler_type_candidate
                return compiler_type_candidate
            candidate_paths.append(compiler_path)
        raise RuntimeError(
            f"Cannot determine compiler type for toolchain at '{self.toolchain_root}'. "
            f"Considered paths: {candidate_paths}.")

    def write_url_and_path_files(self) -> None:
        if self.toolchain_type == 'linuxbrew':
            file_prefix = 'linuxbrew'
        else:
            file_prefix = 'toolchain'

        write_file(os.path.join(YB_THIRDPARTY_DIR, '%s_url.txt' % file_prefix),
                   self.toolchain_url)
        write_file(os.path.join(YB_THIRDPARTY_DIR, '%s_path.txt' % file_prefix),
                   self.toolchain_root)

    def get_llvm_version_str(self) -> str:
        if not self.toolchain_type.startswith('llvm'):
            raise ValueError('Expected an LLVM toolchain type, found: %s' % self.toolchain_type)
        archive_name = os.path.basename(self.toolchain_url)
        url_match = LLVM_VERSION_FROM_ARCHIVE_NAME_RE.match(archive_name)
        if not url_match:
            raise ValueError(
                    'Could not extract LLVM version from download URL: %s' % archive_name)
        return url_match.group(1)


def is_compatible_os_arch_combination(os_arch1: str, os_arch2: str) -> bool:
    os1, arch1 = os_arch1.split('-')
    os2, arch2 = os_arch2.split('-')
    return is_compatible_os_and_version(os1, os2) and arch1 == arch2


def ensure_toolchains_installed(
        download_manager: DownloadManager,
        toolchain_types: List[str]) -> List[Toolchain]:
    return [
        ensure_toolchain_installed(download_manager, toolchain_type)
        for toolchain_type in toolchain_types
    ]


def get_toolchain_url(toolchain_type: str) -> str:
    if toolchain_type == 'linuxbrew':
        # Does not depend on the OS.
        return LINUXBREW_URL

    assert toolchain_type.startswith('llvm')
    local_sys_conf = sys_detection.local_sys_conf()
    major_llvm_version = int(toolchain_type[4:])
    llvm_installer = LlvmInstaller(
        major_llvm_version=major_llvm_version,
        short_os_name_and_version=local_sys_conf.short_os_name_and_version(),
        architecture=local_sys_conf.architecture)
    return llvm_installer.get_llvm_url()


def ensure_toolchain_installed(
        download_manager: DownloadManager,
        toolchain_type: str) -> Toolchain:
    assert toolchain_type in TOOLCHAIN_TYPES, (
        f"Invalid toolchain type: '{toolchain_type}'. Valid types: "
        f"{', '.join(TOOLCHAIN_TYPES)}."
    )

    toolchain_url = get_toolchain_url(toolchain_type)

    if toolchain_type.startswith('llvm'):
        parent_dir = '/opt/yb-build/llvm'
    elif toolchain_type == 'linuxbrew':
        parent_dir = '/opt/yb-build/brew'
    else:
        raise RuntimeError(
            f"We don't know where to install toolchain of type f{toolchain_type}")

    toolchain_root = download_manager.download_toolchain(toolchain_url, parent_dir)

    return Toolchain(
        toolchain_url=toolchain_url,
        toolchain_type=toolchain_type,
        toolchain_root=toolchain_root)
