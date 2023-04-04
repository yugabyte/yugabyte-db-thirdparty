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
import platform

from typing import Optional, List, Tuple
from yugabyte_db_thirdparty.string_util import shlex_join
from yugabyte_db_thirdparty.util import mkdir_if_missing, create_symlink
from yugabyte_db_thirdparty.custom_logging import log

LIBRARY_DIRS_PREFIX = 'libraries: ='


def get_clang_library_dirs(clang_executable_path: str) -> List[str]:
    """
    Returns a list of library directories for Clang by parsing the output of '-print-search-dirs'
    command.
    """
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


def get_clang_library_dir(
        clang_executable_path: str,
        look_for_file: Optional[str] = None,
        all_dirs: bool = False) -> List[str]:
    """
    Finds and returns the Clang runtime library directory using the provided Clang executable path.
    For each of the library directories returned by get_clang_library_dirs(), we will look for a
    a lib/linux or lib/<arch>-unknown-linux-gnu subdirectory. If we find such a subdirectory, we
    will consider returning it (but only if it contains the given file if specified).

    :param clang_executable_path: The path to the Clang executable.
    :param look_for_file: An optional file to look for in the candidate directory. If this file does
                          not exist in the candidate directory, we will continue looking for another
                          candidate directory.
    :param all_dirs: to return all possible directories
    :return: the Clang runtime library directory, or an empty list if not found, or all directories
             if all_dirs is specified.
    """
    library_dirs = get_clang_library_dirs(clang_executable_path)
    candidate_dirs: List[str] = []

    arch = platform.machine()
    arch_specific_subdir_name = f'{arch}-unknown-linux-gnu'
    subdir_names = ['linux', arch_specific_subdir_name]

    found_dirs: List[str] = []

    for library_dir in library_dirs:
        for subdir_name in subdir_names:
            candidate_dir = os.path.join(library_dir, 'lib', subdir_name)
            if os.path.isdir(candidate_dir) and (
                    look_for_file is None or
                    os.path.exists(os.path.join(candidate_dir, look_for_file))):
                if all_dirs:
                    found_dirs.append(candidate_dir)
                else:
                    return [candidate_dir]
            candidate_dirs.append(candidate_dir)

    if (all_dirs and found_dirs) or look_for_file is not None:
        # If we are looking for all directories, return all directories we found. But make sure
        # we found at least one.
        #
        # If we are looking for a specific file, allow returning an empty list if we did not find
        # a directory with that particular file.
        return found_dirs

    for candidate_dir in candidate_dirs:
        log(f"Considered candidate directory: {candidate_dir}")
    raise ValueError(
        "Could not find the Clang runtime library directory by appending lib/... suffixes to "
        "any of the directories returned by 'clang -print-search-dirs' "
        f"(clang path: {clang_executable_path}, subdir names: {subdir_names}, "
        f"file name that must exist in the directory: {look_for_file}): {library_dirs}"
    )


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
        # E.g. for "llvm-ar" we symlink it as both "ar" and "llvm-ar".
        for symlink_name in set([dst_name, os.path.basename(src_name)]):
            create_symlink(
                os.path.join(llvm_bin_dir, src_name),
                os.path.join(tool_dir_path, symlink_name),
                src_must_exist=True
            )
    return True
