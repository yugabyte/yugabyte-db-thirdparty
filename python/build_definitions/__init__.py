#
# Copyright (c) YugaByte, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
# in compliance with the License.  You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied.  See the License for the specific language governing permissions and limitations
# under the License.
#

import os
import sys

import importlib
import pkgutil
import platform
import shutil
import subprocess
import traceback

from typing import Any, List, Optional, Dict, Union, NoReturn
from yugabyte_db_thirdparty.custom_logging import log, fatal
from yugabyte_db_thirdparty.util import YB_THIRDPARTY_DIR
from yugabyte_db_thirdparty.archive_handling import make_archive_name


# -------------------------------------------------------------------------------------------------
# Build groups
# -------------------------------------------------------------------------------------------------

# These are broad groups of dependencies.

# Dependencies that are never instrumented with ASAN/UBSAN or TSAN.
# Also we should not build any C++ code as part of this. Only C code
# TODO: should we actually instrument some of these?
BUILD_GROUP_COMMON = 'build_group_common'

# TODO: this should be called BUILD_GROUP_POTENTIALLY_INSTRUMENTED, because we only instrument these
# dependencies for special builds like ASAN/TSAN.
BUILD_GROUP_INSTRUMENTED = 'build_group_potentially_instrumented'
VALID_BUILD_GROUPS = [BUILD_GROUP_COMMON, BUILD_GROUP_INSTRUMENTED]

# -------------------------------------------------------------------------------------------------
# Build types
# -------------------------------------------------------------------------------------------------

BUILD_TYPE_COMMON = 'common'

# This build type is built with GCC on Linux, unless --custom-clang-prefix is specified.
# In the latter case this is built with Clang and BUILD_TYPE_CLANG_UNINSTRUMENTED is not used.
BUILD_TYPE_UNINSTRUMENTED = 'uninstrumented'

# Clang-based builds with ASAN+UBSAN and TSAN enabled.
BUILD_TYPE_ASAN = 'asan'
BUILD_TYPE_TSAN = 'tsan'

BUILD_TYPE_CLANG_UNINSTRUMENTED = 'clang_uninstrumented'

BUILD_TYPES = [
    BUILD_TYPE_COMMON,
    BUILD_TYPE_UNINSTRUMENTED,
    BUILD_TYPE_CLANG_UNINSTRUMENTED,
    BUILD_TYPE_ASAN,
    BUILD_TYPE_TSAN
]


def unset_env_var_if_set(name: str) -> None:
    if name in os.environ:
        log('Unsetting %s for third-party build (was set to "%s").', name, os.environ[name])
        del os.environ[name]


def is_jenkins_user() -> bool:
    return os.environ['USER'] == "jenkins"


def is_jenkins() -> bool:
    return 'BUILD_ID' in os.environ and 'JOB_NAME' in os.environ and is_jenkins_user()


def import_submodules(package: Any, recursive: bool = True) -> Dict[str, Any]:
    if isinstance(package, str):
        package = importlib.import_module(package)
    results = {}
    for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = package.__name__ + '.' + name
        results[full_name] = importlib.import_module(full_name)
        if recursive and is_pkg:
            results.update(import_submodules(full_name))
    return results


class ExtraDownload:
    def __init__(
            self,
            name: str,
            version: str,
            url_pattern: str,
            dir_name: str,
            post_exec: Union[None, List[str], List[List[str]]] = None) -> None:
        self.name = name
        self.version = version
        self.download_url = url_pattern.format(version)
        self.archive_name = make_archive_name(name, version, self.download_url)
        self.dir_name = dir_name
        self.post_exec = post_exec


def get_build_def_module(submodule_name: str) -> Any:
    return getattr(sys.modules['build_definitions'], submodule_name)
