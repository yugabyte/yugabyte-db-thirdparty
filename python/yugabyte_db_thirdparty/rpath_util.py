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

import glob
import os
import re
import subprocess

from typing import List, Set, Union

from yugabyte_db_thirdparty.custom_logging import log
from sys_detection import is_macos


def get_readelf_rpath_regex_str(path_type: str) -> re.Pattern:
    return re.compile(''.join([
        '^.*[(]',
        path_type.upper(),
        '[)]',
        r'\s+',
        'Library ',
        path_type.lower(),
        ': ',
        r'\[(.*)\]',
    ]))


READELF_LIBRARY_RUNPATH_LINE = get_readelf_rpath_regex_str('runpath')
READELF_LIBRARY_RPATH_LINE = get_readelf_rpath_regex_str('rpath')


def fix_shared_library_references(
        install_prefix: str,
        lib_name_prefix: str) -> None:
    if not is_macos():
        return

    lib_dir = os.path.realpath(os.path.join(install_prefix, "lib"))
    lib_path_glob = os.path.join(lib_dir, lib_name_prefix + "*.dylib")
    lib_paths = glob.glob(lib_path_glob)

    bin_dir = os.path.realpath(os.path.join(install_prefix, "sbin"))
    bin_path_glob = os.path.join(bin_dir, "*")
    bin_paths = glob.glob(bin_path_glob)

    log("Using these glob patterns to look for libraries and executables to fix RPATHs in: %s",
        (lib_path_glob, bin_path_glob))
    if not lib_paths:
        log("Warning: no library paths found using glob %s", lib_path_glob)
    if not bin_paths:
        log("Warning: no executables found using glob %s", bin_path_glob)

    for lib in lib_paths + bin_paths:
        log("Ensuring %s uses @rpath correctly", lib)
        if os.path.islink(lib):
            log("%s is a link, skipping", lib)
            continue

        otool_output = subprocess.check_output(['otool', '-L', lib]).decode('utf-8')
        lib_basename = os.path.basename(lib)

        for line in otool_output.split('\n'):
            if line.startswith('\t' + lib_name_prefix):
                dependency_name = line.strip().split()[0]
                dependency_real_name = os.path.relpath(
                    os.path.realpath(os.path.join(lib_dir, dependency_name)),
                    lib_dir)

                if lib_basename in [dependency_name, dependency_real_name]:
                    log("Making %s refer to itself using @rpath", lib)
                    subprocess.check_call([
                        'install_name_tool',
                        '-id',
                        '@rpath/' + dependency_name,
                        lib
                    ])
                else:
                    log("Making %s refer to %s using @loader_path",
                        lib, dependency_name)
                    subprocess.check_call([
                        'install_name_tool',
                        '-change',
                        dependency_name,
                        '@loader_path/' + dependency_name,
                        lib
                    ])


def get_rpath_flag(path: str) -> str:
    """
    Get the linker flag needed to add the given RPATH to the generated executable or library.
    """
    return "-Wl,-rpath,{}".format(path)


def get_rpaths(file_path: str) -> List[str]:
    candidate_runpaths: Set[str] = set()
    candidate_rpaths_deprecated: Set[str] = set()
    for line in subprocess.check_output(['readelf', '-d', file_path]).decode('utf-8').split('\n'):
        line = line.strip()
        m = READELF_LIBRARY_RUNPATH_LINE.match(line.strip())
        if m:
            candidate_runpaths.add(m.group(1))
        m = READELF_LIBRARY_RPATH_LINE.match(line.strip())
        if m:
            candidate_rpaths_deprecated.add(m.group(1))
    if candidate_rpaths_deprecated:
        raise ValueError(
            f"File {file_path} has the older RPATH attribute. Refusing to work with it.")

    if not candidate_runpaths:
        return []

    if len(candidate_runpaths) > 1:
        raise ValueError(
            f"Contradictory RUNPATH values found for file {file_path}: {candidate_runpaths}")

    runpaths = [item.strip() for item in list(candidate_runpaths)[0].split(':')]
    return [item for item in runpaths if item]


def set_rpaths(file_path: str, rpath_list: List[str]) -> None:
    subprocess.check_call(['patchelf', '--set-rpath', ':'.join(rpath_list), file_path])
    new_rpaths = get_rpaths(file_path)
    if new_rpaths != rpath_list:
        raise ValueError(
            f"Failed to set RPATH on file {file_path} to {rpath_list} using patchelf: "
            f"found {new_rpaths} when re-checked")


def normalize_path_list(paths: Union[str, List[str]]) -> List[str]:
    if isinstance(paths, list):
        return list(paths)
    if isinstance(paths, str):
        return [paths]
    raise ValueError(f"Expected a string or a list of strings, got: {paths}")


def modify_rpaths(
        file_path: str,
        remove: Union[str, List[str]] = [],
        add_first: Union[str, List[str]] = [],
        add_last: Union[str, List[str]] = []) -> None:
    old_rpaths = get_rpaths(file_path)
    set_to_remove = set(normalize_path_list(remove))
    new_rpaths = [p for p in old_rpaths if p not in set_to_remove]
    new_rpaths = normalize_path_list(add_first) + new_rpaths + normalize_path_list(add_last)
    if new_rpaths != old_rpaths:
        set_rpaths(file_path, new_rpaths)
