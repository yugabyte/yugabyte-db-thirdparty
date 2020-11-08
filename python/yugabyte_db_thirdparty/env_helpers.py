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
import shlex

from yugabyte_db_thirdparty.devtoolset import DEVTOOLSET_ENV_VARS
from yugabyte_db_thirdparty.string_util import split_into_word_set


# A mechanism to save some environment variabls to a file in the dependency's build directory to
# make debugging easier.
ENV_VARS_TO_SAVE = split_into_word_set("""
    ASAN_OPTIONS
    CC
    CFLAGS
    CPPFLAGS
    CXX
    CXXFLAGS
    LANG
    LDFLAGS
    PATH
    PYTHONPATH
""")


def write_env_vars(file_path: str) -> None:
    env_script = ''
    for k, v in sorted(dict(os.environ).items()):
        if k in ENV_VARS_TO_SAVE or k in DEVTOOLSET_ENV_VARS or k.startswith('YB_'):
            env_script += '%s=%s\n' % (k, shlex.quote(v))
    with open(file_path, 'w') as output_file:
        output_file.write(env_script)
