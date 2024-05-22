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


import multiprocessing
import os
import re

from typing import Dict, Optional, List

from yugabyte_db_thirdparty.custom_logging import log
from yugabyte_db_thirdparty.util import which_executable
from yugabyte_db_thirdparty.string_util import one_per_line_indented

from yugabyte_db_thirdparty import env_var_names


PLACEHOLDER_RPATH = (
    "/tmp/making_sure_we_have_enough_room_to_set_rpath_later_{}_end_of_rpath".format('_' * 256))
PLACEHOLDER_RPATH_FOR_LOG = '/tmp/long_placeholder_rpath'

CMAKE_VAR_RE = re.compile(r'^(-D[A-Z_]+)=(.*)$')


def get_make_parallelism() -> int:
    return int(os.environ.get(env_var_names.MAKE_PARALLELISM, multiprocessing.cpu_count()))


g_is_ninja_available: Optional[bool] = None


def is_ninja_available() -> bool:
    global g_is_ninja_available
    if g_is_ninja_available is None:
        g_is_ninja_available = bool(which_executable('ninja'))
    return g_is_ninja_available


def sanitize_flags_line_for_log(line: str) -> str:
    return line.replace(PLACEHOLDER_RPATH, PLACEHOLDER_RPATH_FOR_LOG)


def log_and_set_env_var_to_list(
        env_var_map: Dict[str, Optional[str]],
        env_var_name: str,
        items: List[str]) -> None:
    value_str = ' '.join(items).strip()
    if value_str:
        log('Setting env var %s to %s', env_var_name, value_str)
        env_var_map[env_var_name] = value_str
    else:
        log('Unsetting env var %s', env_var_name)
        # When used with EnvVarContext, this will cause the environment variable to be unset.
        env_var_map[env_var_name] = None


def format_cmake_args_for_log(args: List[str]) -> str:
    lines = []
    for arg in args:
        match = CMAKE_VAR_RE.match(arg)
        if match:
            cmake_var_name = match.group(1)
            cmake_var_value = match.group(2)
            cmake_var_value_parts = cmake_var_value.split()
            if len(cmake_var_value_parts) > 1:
                lines.append('%s="%s' % (cmake_var_name, cmake_var_value_parts[0]))
                current_indent = ' ' * (len(cmake_var_name) + 2)
                for cmake_var_value_part in cmake_var_value_parts[1:-1]:
                    lines.append(current_indent + cmake_var_value_part)
                lines.append('%s%s"' % (current_indent, cmake_var_value_parts[-1]))
                continue

        lines.append(arg)

    sanitized_lines = [sanitize_flags_line_for_log(line) for line in lines]
    return one_per_line_indented(sanitized_lines)
