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

# We use Linuxbrew as a portable set of libraries, including glibc and ncurses, that we can build
# our code with so it would run on most Linux systems. The Linuxbrew archive we use includes
# GCC 5.5.0, but we also support building the code for Linuxbrew with Clang 12 (we use the Clang
# package built specifically for the host OS, e.g. RHEL 7 or RHEL 8, not for Linuxbrew).
# Building with a modern version of Clang for Linuxbrew is the preferred build method
# for 12/21/2021.

import os

from sys_detection import is_macos, is_linux

from typing import Optional

from yugabyte_db_thirdparty.custom_logging import log
from yugabyte_db_thirdparty.util import add_path_entry


g_linuxbrew_dir: Optional[str] = None
g_detect_linuxbrew_called: bool = False


def get_optional_linuxbrew_dir() -> Optional[str]:
    global g_detect_linuxbrew_called
    if not g_detect_linuxbrew_called:
        _detect_linuxbrew()
        g_get_optional_linuxbrew_dir_called = True
    return g_linuxbrew_dir


def get_linuxbrew_dir() -> str:
    linuxbrew_dir = get_optional_linuxbrew_dir()
    assert linuxbrew_dir is not None
    return linuxbrew_dir


def _detect_linuxbrew() -> None:
    global g_linuxbrew_dir
    if not is_linux():
        log("Not using Linuxbrew -- this is not Linux")
        return

    linuxbrew_dir_from_env = os.getenv('YB_LINUXBREW_DIR')
    if linuxbrew_dir_from_env:
        g_linuxbrew_dir = linuxbrew_dir_from_env
        log("Setting Linuxbrew directory based on YB_LINUXBREW_DIR env var: %s",
            linuxbrew_dir_from_env)
        return

    # if self.compiler_prefix:
    #     compiler_prefix_basename = os.path.basename(self.compiler_prefix)
    #     if compiler_prefix_basename.startswith('linuxbrew'):
    #         g_linuxbrew_dir = self.compiler_prefix
    #         log("Setting Linuxbrew directory based on compiler prefix %s",
    #             self.compiler_prefix)

    if g_linuxbrew_dir:
        log("Linuxbrew directory: %s", g_linuxbrew_dir)
        new_path_entry = os.path.join(g_linuxbrew_dir, 'bin')
        log("Adding PATH entry: %s", new_path_entry)
        add_path_entry(new_path_entry)
    else:
        log("Not using Linuxbrew")


def using_linuxbrew() -> bool:
    return get_optional_linuxbrew_dir() is not None


def set_linuxbrew_dir(linuxbrew_dir: str) -> None:
    assert not g_detect_linuxbrew_called
    global g_linuxbrew_dir
    if g_linuxbrew_dir is not None and g_linuxbrew_dir != linuxbrew_dir:
        raise ValueError(
            "Linuxbrew directory already set to %s but trying to set it to %s",
            g_linuxbrew_dir, linuxbrew_dir)

    g_linuxbrew_dir = linuxbrew_dir
