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
from typing import Dict, Optional, List

from yugabyte_db_thirdparty.custom_logging import log
from yugabyte_db_thirdparty.util import which_executable


PLACEHOLDER_RPATH = (
    "/tmp/making_sure_we_have_enough_room_to_set_rpath_later_{}_end_of_rpath".format('_' * 256))
PLACEHOLDER_RPATH_FOR_LOG = '/tmp/long_placeholder_rpath'


def get_make_parallelism() -> int:
    return int(os.environ.get('YB_MAKE_PARALLELISM', multiprocessing.cpu_count()))


g_is_ninja_available: Optional[bool] = None


def is_ninja_available() -> bool:
    global g_is_ninja_available
    if g_is_ninja_available is None:
        g_is_ninja_available = bool(which_executable('ninja'))
    return g_is_ninja_available


def get_rpath_flag(path: str) -> str:
    """
    Get the linker flag needed to add the given RPATH to the generated executable or library.
    """
    return "-Wl,-rpath,{}".format(path)


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
