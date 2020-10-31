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

"""
Support for CentOS/RedHat devtoolsets.
"""

import os
import subprocess

from typing import Set
from yugabyte_db_thirdparty.util import log
from yugabyte_db_thirdparty.string_util import split_into_word_set


DEVTOOLSET_ENV_VARS: Set[str] = split_into_word_set("""
    INFOPATH
    LD_LIBRARY_PATH
    MANPATH
    PATH
    PCP_DIR
    PERL5LIB
    PKG_CONFIG_PATH
    PYTHONPATH
""")

DEVTOOLSET_ENV_VARS_OK_IF_UNSET: Set[str] = set(['PERL5LIB'])


def activate_devtoolset(devtoolset_number: int) -> None:
    devtoolset_enable_script = (
        '/opt/rh/devtoolset-%d/enable' % devtoolset_number
    )
    log("Enabling devtoolset-%s by sourcing the script %s",
        devtoolset_number, devtoolset_enable_script)
    if not os.path.exists(devtoolset_enable_script):
        raise IOError("Devtoolset script does not exist: %s" % devtoolset_enable_script)

    cmd_args = ['bash', '-c', '. "%s" && env' % devtoolset_enable_script]
    log("Running command: %s", cmd_args)
    devtoolset_env_str = subprocess.check_output(cmd_args).decode('utf-8')

    found_vars = set()
    for line in devtoolset_env_str.split("\n"):
        line = line.strip()
        if not line:
            continue
        k, v = line.split("=", 1)
        if k in DEVTOOLSET_ENV_VARS:
            log("Setting %s to: %s", k, v)
            os.environ[k] = v
            found_vars.add(k)
    missing_vars = set()
    for var_name in DEVTOOLSET_ENV_VARS:
        if var_name not in found_vars:
            log("Did not set env var %s for devtoolset-%d", var_name, devtoolset_number)
            if var_name not in DEVTOOLSET_ENV_VARS_OK_IF_UNSET:
                missing_vars.add(var_name)
    if missing_vars:
        raise IOError(
            "Invalid environment after running devtoolset script %s. Did not set vars: %s" % (
                devtoolset_enable_script, ', '.join(sorted(missing_vars))
            ))
