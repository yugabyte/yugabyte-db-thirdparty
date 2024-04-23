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

import os
import re

from typing import List, Optional, Set

from yugabyte_db_thirdparty.util import capture_all_output


LDD_ENV = {'LC_ALL': 'en_US.UTF-8'}

RESOLVED_DEPENDENCY_RE = re.compile(r'^(\S*) => (\S*) [(]0x[0-9a-f]+[)]$')

SHARED_LIB_SUFFIX_RE = re.compile(r'^(.*)[.]so([.\d]+)?$')


class LddResult:
    file_path: str
    output_lines: List[str]
    _resolved_dependencies: Optional[Set[str]]

    def __init__(self, file_path: str, output_lines: List[str]) -> None:
        self.file_path = file_path
        self.output_lines = output_lines
        self._resolved_dependencies = None

    def not_a_dynamic_executable(self) -> bool:
        """
        Checks if the output says that this is not a dynamic executable.
        """
        return any(['not a dynamic executable' in line for line in self.output_lines])

    @property
    def resolved_dependencies(self) -> Set[str]:
        if self._resolved_dependencies is not None:
            return self._resolved_dependencies
        result: Set[str] = set()
        for line in self.output_lines:
            match = RESOLVED_DEPENDENCY_RE.match(line.strip())
            if match:
                result.add(match.group(2))
        self._resolved_dependencies = result
        return result


def is_elf_file(file_path: str) -> bool:
    with open(file_path, 'rb') as file:
        # Read the first 4 bytes of the file
        header = file.read(4)
        # Check if the bytes match the ELF magic number
        return header == b'\x7fELF'


def should_use_ldd_on_file(file_path: str) -> bool:
    """
    Checks if it makes sense to use ldd on the given file. In addition to other criteria, returns
    true for any executable file, even if it might turn out to be a script.
    """
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return False
    return (
        os.access(file_path, os.X_OK) or
        file_path.endswith('.so') or
        '.so.' in os.path.basename(file_path) or
        is_elf_file(file_path)
    )


def run_ldd(file_path: str) -> LddResult:
    return LddResult(
        file_path=file_path,
        output_lines=capture_all_output(
            ['ldd', file_path],
            env=LDD_ENV,
            allowed_exit_codes={1}))


def remove_shared_lib_suffix(shared_lib_path: str) -> str:
    """
    >>> remove_shared_lib_suffix('/opt/intel/oneapi/mkl/2024.1/lib/libmkl_intel_ilp64.so')
    '/opt/intel/oneapi/mkl/2024.1/lib/libmkl_intel_ilp64'
    >>> remove_shared_lib_suffix('libmkl_intel_thread.so.2')
    'libmkl_intel_thread'
    """
    match = SHARED_LIB_SUFFIX_RE.match(shared_lib_path)
    assert match, f"Unknown shared library name format: {os.path.basename(shared_lib_path)}"
    return match.group(1)
