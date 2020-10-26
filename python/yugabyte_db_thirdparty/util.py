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
import sys
import hashlib
import shutil

from yugabyte_db_thirdparty.custom_logging import log, fatal
from typing import List, Optional, Any


def assert_list_contains(items: List[str], required_item: str) -> None:
    if required_item not in items:
        raise ValueError("%s not found in %s" % (required_item, items))


def indent_lines(s: Optional[str], num_spaces: int = 4) -> Optional[str]:
    if s is None:
        return s
    return "\n".join([
        ' ' * num_spaces + line for line in s.split("\n")
    ])


def hashsum_file(hash: Any, filename: str, block_size: int = 65536) -> str:
    """
    Compute the hash sun of a file by updating the existing hash object.
    """
    # TODO: use a more precise argument type for hash.
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            hash.update(block)
    return hash.hexdigest()


def compute_file_sha256(path: str) -> str:
    return hashsum_file(hashlib.sha256(), path)


def replace_string_in_file(
        path: str,
        str_to_replace: str,
        str_to_replace_with: str,
        backup_extension: str = '.bak') -> int:
    """
    Replaces all occurrences of a string in a file with a given new string. Returns the number of
    modified lines.
    """
    if not backup_extension.startswith('.'):
        backup_extension = '.' + backup_extension
    shutil.copyfile(path, path + backup_extension)
    processed_lines = []
    num_modified_lines = 0
    with open(path) as input_file:
        for line in input_file:
            modified_line = line.replace(str_to_replace, str_to_replace_with)
            if line != modified_line:
                num_modified_lines += 1
            processed_lines.append(modified_line)
    with open(path, 'w') as output_file:
        for line in processed_lines:
            output_file.write(line)
    return num_modified_lines


def remove_path(path: str) -> None:
    if os.path.islink(path):
        # Remove the link even if the path it is pointing to does not exist.
        os.unlink(path)
    if not os.path.exists(path):
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def mkdir_if_missing(path: str) -> None:
    if os.path.exists(path):
        if not os.path.isdir(path):
            fatal("Trying to create dir {}, but file with the same path already exists"
                  .format(path))
        return
    os.makedirs(path)


def does_file_start_with_string(file_path: str, s: str) -> bool:
    if not os.path.exists(file_path):
        return False
    with open(file_path) as f:
        return f.read().strip().startswith(s)


class PushDir:
    dir_name: str
    prev: Optional[str]

    def __init__(self, dir_name: str) -> None:
        self.dir_name = dir_name
        self.prev = None

    def __enter__(self) -> None:
        self.prev = os.getcwd()
        os.chdir(self.dir_name)

    def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
        # TODO: use more precise argument types above.
        assert self.prev is not None
        os.chdir(self.prev)


def which_executable(cmd_name: str) -> Optional[str]:
    result = shutil.which(cmd_name)
    if result is None:
        return result
    assert isinstance(result, str)
    return result


def which_must_exist(cmd_name: str) -> str:
    result = which_executable(cmd_name)
    if result is None:
        raise IOError("Executable not found: %s. PATH: %s" % (cmd_name, os.getenv('PATH')))
    return result


def copy_file_and_log(src_path: str, dst_path: str) -> None:
    log(f"Copying file {os.path.abspath(src_path)} to {os.path.abspath(dst_path)}")
    shutil.copyfile(src_path, dst_path)
