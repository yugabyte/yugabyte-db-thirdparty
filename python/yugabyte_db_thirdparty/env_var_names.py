# Copyright (c) YugabyteDB, Inc.
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

# Constants in this module are supposed to be environment variable names.

import sys
import re


# Set these to empty strings, and they will be automatically set to YB_THIRDPARTY_<name>,
# e.g. YB_THIRDPARTY_LD_FLAGS_TO_APPEND.
LD_FLAGS_TO_APPEND = ''
LD_FLAGS_TO_REMOVE = ''
TRACK_INCLUDES_IN_SUBDIRS_OF = ''
SAVE_USED_INCLUDE_TAGS_IN_DIR = ''
DISALLOWED_INCLUDE_DIRS = ''
DISALLOWED_INCLUDE_DIR_PREFIXES = ''
CONFIGURING = ''


def _set_env_var_constants() -> None:
    env_var_name_re = re.compile('^[A-Z0-9_]+$')

    current_module = sys.modules[__name__]

    # Dynamically set constants in the current module with values derived from their name.
    for constant_name in dir(current_module):
        if not env_var_name_re.match(constant_name):
            continue
        existing_val = getattr(current_module, constant_name)
        if existing_val != '':
            continue

        setattr(current_module, constant_name, 'YB_THIRDPARTY_' + constant_name)


_set_env_var_constants()
