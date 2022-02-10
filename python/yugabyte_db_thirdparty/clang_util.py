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

import subprocess
import os
from typing import Optional, List, Tuple
from yugabyte_db_thirdparty.string_util import shlex_join
from yugabyte_db_thirdparty.util import mkdir_if_missing, create_symlink
from yugabyte_db_thirdparty.custom_logging import log

LIBRARY_DIRS_PREFIX = 'libraries: ='


def get_clang_library_dirs(clang_executable_path: str) -> List[str]:
    search_dirs_cmd = [clang_executable_path, '-print-search-dirs']
    search_dirs_output = subprocess.check_output(search_dirs_cmd).decode('utf-8')
    library_dirs: Optional[List[str]] = None
    for line in search_dirs_output.split('\n'):
        line = line.strip()
        if line.startswith(LIBRARY_DIRS_PREFIX):
            library_dirs = [s.strip() for s in line[len(LIBRARY_DIRS_PREFIX):].split(':')]
            break
    if library_dirs is None:
        raise ValueError(
            f"Could not find a line starting with '{LIBRARY_DIRS_PREFIX}' in the "
            f"output of the command: {shlex_join(search_dirs_cmd)}:\n{search_dirs_output}")
    return library_dirs


def get_clang_library_dir(clang_executable_path: str) -> str:
    library_dirs = get_clang_library_dirs(clang_executable_path)
    candidate_dirs: List[str] = []
    for library_dir in library_dirs:
        candidate_dir = os.path.join(library_dir, 'lib', 'linux')
        if os.path.isdir(candidate_dir):
            return candidate_dir
        candidate_dirs.append(candidate_dir)

    raise ValueError(
        f"Could not find a 'lib/linux' subdirectory in any of the library directories "
        f"returned by 'clang -print-search-dirs' (clang path: {clang_executable_path}):\n"
        f"{library_dirs}\n.Considered candidate directories:{candidate_dirs}")


def get_clang_include_dir(clang_executable_path: str) -> str:
    """
    Returns a directory such as lib/clang/13.0.1/include relative to the LLVM installation path.
    """
    library_dirs = get_clang_library_dirs(clang_executable_path)
    for library_dir in library_dirs:
        include_dir = os.path.join(library_dir, 'include')
        if os.path.isdir(include_dir):
            return include_dir
    raise ValueError(
        f"Could not find a directory from {library_dirs} that has an 'include' subdirectory.")


def get_clang_libcxx_include_dir(clang_executable_path: str) -> str:
    """
    Returns a directory such as include/c++/v1 containing libc++ installation headers. This is
    needed to bootstrap the libc++abi build with Clang 13 and later.
    """
    llvm_bin_dir = os.path.dirname(os.path.abspath(clang_executable_path))
    llvm_installation_dir = os.path.dirname(llvm_bin_dir)
    include_dir = os.path.join(llvm_installation_dir, 'include', 'c++', 'v1')
    if not os.path.isdir(include_dir):
        raise IOError(
            "libc++ include directory of the LLVM installation not found at %s" % include_dir)
    return include_dir


def create_llvm_tool_dir(clang_path: str, tool_dir_path: str) -> bool:
    """
    Create a directory with symlinks named like the standard tools used for compiling UNIX programs
    (ar, nm, ranlib, ld, et.) but pointing to LLVM counterparts of these tools.
    """
    if not os.path.abspath(clang_path).endswith('/bin/clang'):
        log("Clang compiler path does not end with '/bin/clang', not creating a directory with "
            "LLVM tools to put on PATH. Clang path: %s" % clang_path)
        return False

    mkdir_if_missing(tool_dir_path)
    llvm_bin_dir = os.path.dirname(os.path.abspath(clang_path))
    # llvm-as does not work properly when substituted for the as command. Don't add it here.
    src_dst_names: List[Tuple[str, str]] = [
        ('llvm-%s' % tool_name, tool_name) for tool_name in [
            'ar',
            'nm',
            'ranlib',
        ]
    ] + [('lld', 'ld')]
    for src_name, dst_name in src_dst_names:
        create_symlink(
            os.path.join(llvm_bin_dir, src_name),
            os.path.join(tool_dir_path, dst_name),
            src_must_exist=True
        )
    return True
