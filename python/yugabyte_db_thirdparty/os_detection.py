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

import platform
import os_release  # type: ignore
from yugabyte_db_thirdparty.util import does_file_start_with_string

from typing import Optional, Any


_linux_os_release = None


def is_mac() -> bool:
    return platform.system().lower() == 'darwin'


def is_linux() -> bool:
    return platform.system().lower() == 'linux'


def get_linux_os_release() -> Any:
    if not is_linux():
        return None

    global _linux_os_release
    if _linux_os_release is None:
        _linux_os_release = os_release.current_release()
    return _linux_os_release


def linux_release_name_starts_with(prefix: str) -> bool:
    return is_linux() and get_linux_os_release().name.lower().startswith(prefix.lower())


def is_ubuntu() -> bool:
    return linux_release_name_starts_with('ubuntu')


def is_centos() -> bool:
    return linux_release_name_starts_with('centos')


def is_almalinux() -> bool:
    return linux_release_name_starts_with('almalinux')


def is_redhat() -> bool:
    return linux_release_name_starts_with('red hat')


def is_redhat_family() -> bool:
    return is_centos() or is_almalinux() or is_redhat()
