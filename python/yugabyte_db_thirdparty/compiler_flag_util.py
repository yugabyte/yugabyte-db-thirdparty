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

from typing import List, Set

from yugabyte_db_thirdparty import constants


CXX_STANDARD_FLAG_PREFIX = '-std=c++'


def is_cxx_standard_flag(flag: str) -> str:
    return flag.startswith(CXX_STANDARD_FLAG_PREFIX)


def get_cxx_standard_flag_set(cmd_args: List[str]) -> Set[str]:
    cxx_standard_args: Set[str] = set()
    for arg in cmd_args:
        if is_cxx_standard_flag(arg):
            cxx_standard_args.add(arg[len(CXX_STANDARD_FLAG_PREFIX):])
    return cxx_standard_args


def remove_incorrect_cxx_standard_flags(cmd_args: List[str]) -> List[str]:
    return [
        arg for arg in cmd_args
        if not (is_cxx_standard_flag(arg) and
                arg[len(CXX_STANDARD_FLAG_PREFIX):] != str(constants.CXX_STANDARD))
    ]