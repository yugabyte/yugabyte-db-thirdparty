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
import sys
import re
import subprocess
import platform

from typing import List
from build_definitions import (
    log,
    heading,
    BUILD_TYPES,
    fatal,
    is_mac,
    is_linux
)


def compile_re_list(re_list: List[str]) -> Any:
    self.okay_paths = re.compile("|".join(re_list))


class LibTestBase:
    """
    Verify correct library paths are used in installed dynamically-linked executables and
    libraries.
    """
    lib_re_list: List[str]
    bad_lib_re_list: List[str]
    tool: str

    def __init__(self) -> None:
        self.tp_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
        self.tp_installed_dir = os.path.join(self.tp_dir, 'installed')
        self.lib_re_list = []
        self.bad_lib_re_list = []

    def init_regex(self) -> None:
        self.okay_paths = compile_re_list(self.lib_re_list)
        if self.bad_lib_re_list:
            self.bad_lib_re = compile_re_list(bad_lib_re_list)

    def check_lib_deps(self, file_path: str, cmdout: str) -> bool:
        status = True
        for line in cmdout.splitlines():
            if (not self.okay_paths.match(line) or
                (self.bad_lib_re_list and self.bad_lib_re.match(line))):
                if status:
                    log(file_path + ":")
                log("Bad path: %s", line)
        return status

    # overridden in platform specific classes
    def good_libs(self, file_path: str) -> bool:
        raise NotImplementedError()

    def run(self) -> None:
        self.init_regex()
        heading("Scanning installed executables and libraries...")
        test_pass = True
        # files to examine are much reduced if we look only at bin and lib directories
        dir_pattern = re.compile('^(lib|libcxx|[s]bin)$')
        dirs = [os.path.join(self.tp_installed_dir, type) for type in BUILD_TYPES]
        for installed_dir in dirs:
            with os.scandir(installed_dir) as candidate_dirs:
                for candidate in candidate_dirs:
                    if dir_pattern.match(candidate.name):
                        examine_path = os.path.join(installed_dir, candidate.name)
                        for dirpath, dirnames, files in os.walk(examine_path):
                            for file_name in files:
                                full_path = os.path.join(dirpath, file_name)
                                if os.path.islink(full_path):
                                    continue
                                if not self.good_libs(full_path):
                                    test_pass = False
        if not test_pass:
            fatal(f"Found problematic library dependencies, using tool: {self.tool}")
        else:
            log("No problems found with library dependencies.")


class LibTestMac(LibTestBase):
    def __init__(self) -> None:
        super().__init__()
        self.tool = "otool -L"
        self.lib_re_list = ["^\t/usr/",
                            "^\t/System/Library/",
                            "^Archive ",
                            "^/",
                            "^\t@rpath",
                            "^\t@loader_path",
                            f"^\t{self.tp_dir}"]

    def good_libs(self, file_path: str) -> bool:
        libout = subprocess.check_output(['otool', '-L', file_path]).decode('utf-8')
        if 'is not an object file' in libout:
            return True
        return self.check_lib_deps(file_path, libout)


class LibTestLinux(LibTestBase):
    def __init__(self) -> None:
        super().__init__()
        self.tool = "ldd"
        self.lib_re_list = [
            "^\tlinux-vdso",
            "^\t/lib64/",
            "^\t/opt/yb-build/brew/linuxbrew",
            "^\tstatically linked",
            "^\tnot a dynamic executable",
            "ldd: warning: you do not have execution permission",
            "^.* => /lib64/",
            "^.* => /lib/",
            "^.* => /usr/lib/x86_64-linux-gnu/",
            "^.* => /opt/yb-build/brew/linuxbrew",
            f"^.* => {self.tp_dir}"
        ]

    def good_libs(self, file_path: str) -> bool:
        try:
            libout = subprocess.check_output(
                ['ldd', file_path],
                stderr=subprocess.STDOUT, env={'LC_ALL': 'en_US.UTF-8'}).decode('utf-8')
        except subprocess.CalledProcessError as ex:
            if ex.returncode > 1:
                log("Unexpected exit code %d from ldd, file %s", ex.returncode, file_path)
                log(ex.stdout.decode('utf-8'))
                return False

            libout = ex.stdout.decode('utf-8')
        return self.check_lib_deps(file_path, libout)


def get_lib_tester() -> LibTestBase:
    if is_mac():
        return LibTestMac()
    if is_linux():
        return LibTestLinux()

    fatal(f"Unsupported platform: {platform.system()}")
