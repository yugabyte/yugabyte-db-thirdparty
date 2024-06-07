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
#

import os
import re
import subprocess

from typing import List, Optional, Dict

from packaging.version import parse as parse_version

from yugabyte_db_thirdparty import util


PATCHELF_VERSION_OUTPUT_RE = re.compile(r'^patchelf (\d|\d[\d.]*\d)$')


system_patchelf_resolved = False
system_patchelf_path: Optional[str] = None

custom_patchelf_path: Optional[str] = None

patchelf_version_cache: Dict[str, str] = {}


def get_patchelf_version(patchelf_path: str) -> str:
    patchelf_path = os.path.realpath(patchelf_path)

    if patchelf_path in patchelf_version_cache:
        return patchelf_version_cache[patchelf_path]

    patchelf_version_output_str = \
        subprocess.check_output([patchelf_path, '--version']).decode('utf-8').strip()

    match = PATCHELF_VERSION_OUTPUT_RE.match(patchelf_version_output_str)
    if not match:
        raise ValueError(
            f"Unable to parse patchelf version for executable at {patchelf_path}: "
            f"{patchelf_version_output_str}")

    version_str = match.group(1)

    patchelf_version_cache[patchelf_path] = version_str
    return version_str


def set_custom_patchelf_path(patchelf_path: str) -> None:
    global custom_patchelf_path
    custom_patchelf_path = patchelf_path


def get_custom_patchelf_path() -> str:
    assert custom_patchelf_path is not None
    return custom_patchelf_path


def get_patchelf_path() -> str:
    global system_patchelf_resolved, system_patchelf_path
    if not system_patchelf_resolved:
        system_patchelf_path = util.which_executable('patchelf')
        system_patchelf_resolved = True

    highest_version_path: Optional[str] = None
    candidate_paths = sorted(
        p for p in [system_patchelf_path, custom_patchelf_path] if p
    )
    for candidate_path in candidate_paths:
        if os.path.exists(candidate_path) and (
                highest_version_path is None or
                get_patchelf_version(candidate_path) > get_patchelf_version(highest_version_path)):
            highest_version_path = candidate_path
    if highest_version_path is None:
        raise ValueError(
            "Could not find a working patchelf tool at any of these paths: " +
            str(candidate_paths))
    return highest_version_path
