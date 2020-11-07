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

from yugabyte_db_thirdparty.os_detection import is_mac
from yugabyte_db_thirdparty.custom_logging import log


def fix_library_references_to_use_rpath(
        install_prefix: str,
        lib_name_prefix: str) -> None:
    if not is_mac():
        return

    lib_dir = os.path.realpath(os.path.join(install_prefix, "lib"))
    lib_paths = glob.glob(os.path.join(lib_dir, lib_name_prefix + "*.dylib"))

    bin_dir = os.path.realpath(os.path.join(install_prefix, "sbin"))
    bin_paths = glob.glob(os.path.join(bin_dir, "*"))

    for lib in lib_paths + bin_paths:
        if os.path.islink(lib):
            continue
        lib_basename = os.path.basename(lib)

        otool_output = subprocess.check_output(['otool', '-L', lib]).decode('utf-8')

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
