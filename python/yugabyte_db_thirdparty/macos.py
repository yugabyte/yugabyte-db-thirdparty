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

from yugabyte_db_thirdparty.arch import get_target_arch
from sys_detection import is_macos


def get_min_supported_macos_version() -> str:
    assert is_macos()
    return '11.2'


def get_macos_sysroot() -> str:
    candidates = list(glob.glob(
        '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/'
        'MacOSX*.sdk'))
    candidates.extend(glob.glob('/Library/Developer/CommandLineTools/SDKs/MacOSX*.sdk'))
    if not candidates:
        raise RuntimeError("No Xcode SDKs found")
    candidates.sort()
    return candidates[-1]
