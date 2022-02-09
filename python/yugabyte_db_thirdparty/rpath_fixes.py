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
import glob
import subprocess

from sys_detection import is_macos
from yugabyte_db_thirdparty.custom_logging import log


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
