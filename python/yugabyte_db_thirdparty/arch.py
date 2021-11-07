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
import platform

from sys_detection import is_macos
from typing import List, Optional


g_target_arch: Optional[str] = None


def get_target_arch() -> str:
    global g_target_arch

    if g_target_arch is not None:
        return g_target_arch

    if not is_macos():
        g_target_arch = platform.machine()
        return g_target_arch

    g_target_arch = os.getenv('YB_TARGET_ARCH')
    if g_target_arch not in ['x86_64', 'arm64']:
        raise ValueError("Unsupported value of YB_TARGET_ARCH on maOS: %s" % g_target_arch)

    return g_target_arch


def verify_arch() -> None:
    target_arch = get_target_arch()
    actual_arch = platform.machine()
    if actual_arch != target_arch:
        raise ValueError("Expected to be running under the %s architecture, got %s" % (
            target_arch, actual_arch))


def get_arch_switch_cmd_prefix() -> List[str]:
    """
    Returns a command line prefix that will switch to the target architecture.
    """
    if not is_macos():
        return []
    actual_arch = platform.machine()
    target_arch = get_target_arch()
    if actual_arch == target_arch:
        return []
    return ['arch', '-%s' % target_arch]
