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


TOOLCHAIN_TO_OS_AND_ARCH_TO_URL = {
    'llvm11': {
        'centos7-x86_64':     get_llvm_url('v11.1.0-yb-1-1633099975-130bd22e-centos7-x86_64'),
        'centos8-aarch64':    get_llvm_url('v11.1.0-yb-1-1633544021-130bd22e-centos8-aarch64'),
        'almalinux8-x86_64':  get_llvm_url('v11.1.0-yb-1-1633143292-130bd22e-almalinux8-x86_64'),
        'amzn2-aarch64':      get_llvm_url('v11.1.0-yb-1-1647671171-130bd22e-amzn2-aarch64'),
    },
    'llvm12': {
        'centos7-x86_64':     get_llvm_url('v12.0.1-yb-1-1633099823-bdb147e6-centos7-x86_64'),
        'almalinux8-x86_64':  get_llvm_url('v12.0.1-yb-1-1633143152-bdb147e6-almalinux8-x86_64'),
        'amzn2-aarch64':      get_llvm_url('v12.0.1-yb-1-1647674838-bdb147e6-amzn2-aarch64'),
    },
    'llvm13': {
        'centos7-x86_64':     get_llvm_url('v13.0.1-yb-1-1644383736-191e3a05-centos7-x86_64'),
        'centos8-aarch64':    get_llvm_url('v13.0.0-yb-1-1639976983-4b60e646-centos8-aarch64'),
        'almalinux8-x86_64':  get_llvm_url('v13.0.1-yb-1-1644390288-191e3a05-almalinux8-x86_64'),
        'amzn2-aarch64':      get_llvm_url('v13.0.1-yb-1-1647678956-191e3a05-amzn2-aarch64'),
    },
    'llvm14': {
        'centos7-x86_64':     get_llvm_url('v14.0.0-1648392050-329fda39-centos7-x86_64'),
        'almalinux8-aarch64': get_llvm_url('v14.0.0-1648380033-329fda39-almalinux8-aarch64'),
        'amzn2-aarch64':      get_llvm_url('v14.0.0-1648379878-329fda39-amzn2-aarch64'),
        'almalinux8-x86_64':  get_llvm_url('v14.0.0-1648363631-329fda39-almalinux8-x86_64'),
    },
}

TOOLCHAIN_TYPES = sorted(TOOLCHAIN_TO_OS_AND_ARCH_TO_URL.keys()) + [
    'linuxbrew'
] + ['llvm%d_linuxbrew' % v for v in [11, 12, 13, 14]]


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

    os_and_arch_to_url = TOOLCHAIN_TO_OS_AND_ARCH_TO_URL[toolchain_type]
    local_sys_conf = sys_detection.local_sys_conf()
    os_and_arch = local_sys_conf.id_for_packaging()
    if os_and_arch in os_and_arch_to_url:
        toolchain_url = os_and_arch_to_url[os_and_arch]
    else:
        os_and_arch_candidates = []
        for os_and_arch_candidate in os_and_arch_to_url.keys():
            if is_compatible_os_arch_combination(os_and_arch_candidate, os_and_arch):
                os_and_arch_candidates.append(os_and_arch_candidate)
        err_msg_prefix = (
            f"Toolchain {toolchain_type} not found for OS/architecture combination {os_and_arch}")
        if not os_and_arch_candidates:
            raise ValueError(
                    f"{err_msg_prefix}, and no compatible OS/architecture combinations found.")
        if len(os_and_arch_candidates) > 1:
            raise ValueError(
                    f"{err_msg_prefix}, and too many compatible OS/architecture combinations "
                    "found, cannot choose automatically: {os_and_arch_candidates}")
        effective_os_and_arch = os_and_arch_candidates[0]
        toolchain_url = os_and_arch_to_url[effective_os_and_arch]
    return toolchain_url


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
