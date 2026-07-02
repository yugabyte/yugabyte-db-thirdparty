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

from typing import List, Set, Union

from yugabyte_db_thirdparty import constants


CXX_STANDARD_FLAG_PREFIX = '-std=c++'


def is_cxx_standard_flag(flag: str) -> bool:
    """
    Returns true if the given compiler flag specifies the C++ standard version.
    """
    return flag.startswith(CXX_STANDARD_FLAG_PREFIX)


def get_cxx_standard_version_from_flag(flag: str) -> str:
    flag = flag.strip()
    assert flag.startswith(CXX_STANDARD_FLAG_PREFIX)
    cxx_standard_version = flag[len(CXX_STANDARD_FLAG_PREFIX):]
    assert cxx_standard_version
    return cxx_standard_version


def is_correct_cxx_standard_version(version: Union[int, str]) -> bool:
    return str(version) == str(constants.CXX_STANDARD)


def get_cxx_standard_version_set(cmd_args: List[str]) -> Set[str]:
    """
    Collects the set of C++ standard versions that are specified by flags present in the given list
    of C++ compiler flags.
    """
    cxx_standard_args: Set[str] = set()
    for arg in cmd_args:
        if is_cxx_standard_flag(arg):
            cxx_standard_args.add(get_cxx_standard_version_from_flag(arg))
    return cxx_standard_args


def remove_incorrect_cxx_standard_flags(cmd_args: List[str]) -> List[str]:
    """
    Returns a new list of compiler arguments that is obtained from the given list by removing all
    arguments that specify an incorrect version of the C++ standard. All of the dependencies we
    are building must use the same version of the C++ standard.
    """
    return [
        arg for arg in cmd_args
        if (not is_cxx_standard_flag(arg) or
            is_correct_cxx_standard_version(get_cxx_standard_version_from_flag(arg)))
    ]
