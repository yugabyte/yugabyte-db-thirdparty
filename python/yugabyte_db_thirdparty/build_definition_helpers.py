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


# All symbols from this files are imported using a wildcard import into each build definition
# module. This allows to refactor code referenced from this file without modifying each build
# definition module.

from yugabyte_db_thirdparty.builder_interface import BuilderInterface
from yugabyte_db_thirdparty.dependency import Dependency
from yugabyte_db_thirdparty.custom_logging import log, log_output, fatal
from yugabyte_db_thirdparty.util import (
    mkdir_if_missing,
    PushDir,
    remove_path,
    copy_file_and_log
)
from yugabyte_db_thirdparty.arch import is_macos_arm64_build
from yugabyte_db_thirdparty.rpath_fixes import fix_shared_library_references

from build_definitions import (
    BUILD_GROUP_COMMON,
    BUILD_GROUP_INSTRUMENTED,
    BUILD_TYPE_ASAN,
    BUILD_TYPE_TSAN,
)

from typing import List, Dict, Set, Any
from sys_detection import is_linux, is_macos
