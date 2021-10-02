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

from typing import Optional

import sys_detection
from sys_detection import SHORT_OS_NAME_REGEX_STR


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
    'linuxbrew': {
        'centos7-x86_64': LINUXBREW_URL,
    },
    'llvm7': {
        'centos7-x86_64': get_llvm_url('v7.1.0-1617644423-4856a933'),
    },
    'llvm11': {
        'centos7-x86_64': get_llvm_url('v11.1.0-yb-1-1633099975-130bd22e-centos7-x86_64'),
        'almalinux8-x86_64': get_llvm_url('v11.1.0-yb-1-1633143292-130bd22e-almalinux8-x86_64'),
    },
    'llvm12': {
        'centos7-x86_64': get_llvm_url('v12.0.1-yb-1-1633099823-bdb147e6-centos7-x86_64'),
        'almalinux8-x86_64': get_llvm_url('v12.0.1-yb-1-1633143152-bdb147e6-almalinux8-x86_64'),
    }
}

TOOLCHAIN_TYPES = sorted(TOOLCHAIN_TO_OS_AND_ARCH_TO_URL.keys())


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
        write_file(os.path.join(YB_THIRDPARTY_DIR, 'toolchain_url.txt'),
                   self.toolchain_url)
        write_file(os.path.join(YB_THIRDPARTY_DIR, 'toolchain_path.txt'),
                   self.toolchain_root)
        if self.toolchain_type == 'linuxbrew':
            # TODO: remove this after the YugabyteDB build system is upgraded to only look at
            # toolchain_{url,path}.txt.
            write_file(os.path.join(YB_THIRDPARTY_DIR, 'linuxbrew_url.txt'),
                       self.toolchain_url)
            write_file(os.path.join(YB_THIRDPARTY_DIR, 'linuxbrew_path.txt'),
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


def ensure_toolchain_installed(
        download_manager: DownloadManager,
        toolchain_type: str) -> Toolchain:
    assert toolchain_type in TOOLCHAIN_TYPES, (
        f"Invalid toolchain type: '{toolchain_type}'. Valid types: "
        f"{', '.join(TOOLCHAIN_TYPES)}."
    )

    os_and_arch_to_url = TOOLCHAIN_TO_OS_AND_ARCH_TO_URL[toolchain_type]
    local_sys_conf = sys_detection.local_sys_conf()
    os_and_arch = local_sys_conf.id_for_packaging()
    if os_and_arch not in os_and_arch_to_url:
        raise ValueError(
                f"Toolchain {toolchain_type} not found for OS/architecture combination "
                f"{os_and_arch}")

    toolchain_url = os_and_arch_to_url[os_and_arch]
    compiler_type = None
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
