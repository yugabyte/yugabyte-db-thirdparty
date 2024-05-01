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

import os
import pathlib
import shutil

from yugabyte_db_thirdparty.custom_logging import log


def mkdir_p(path: str) -> None:
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


def create_intermediate_dirs_for_rel_path(
        base_dir: str,
        rel_path: str) -> str:
    """
    Creates all intermatediate directories between the given base directory and the given
    relative path, so that a file or directory named os.path.join(bas_dir, rel_path) could be
    created.

    :return: the deepest directory created
    """
    assert not os.path.isabs(rel_path)
    assert os.path.isdir(base_dir)

    cur_dir = base_dir
    path_components = pathlib.Path(rel_path).parts
    for component in path_components[:-1]:
        cur_dir = os.path.join(cur_dir, component)
        if not os.path.isdir(cur_dir):
            os.mkdir(cur_dir)

    return cur_dir


def copy_simple_file_name_symlink(existing_link: str, dest_path: str) -> None:
    """
    Create a symbolic link at the destination path, pointing to the same relative path as the
    specified existing link. The link target path is expected to be a file name, not an absolute
    path or a relative path containing a directory.
    """
    assert os.path.islink(existing_link)
    link_target = os.readlink(existing_link)
    assert '/' not in link_target, \
        f"Expected symlink target {link_target} of " \
        f"{existing_link} to be a file name only."
    log(f"Symlinking {dest_path} -> {link_target}")
    os.symlink(link_target, dest_path)


def copy_file_or_simple_symlink(path_to_copy: str, dest_path: str) -> None:
    """
    Copies the given file or symlink to the given destination path. If it is a symlink, it is
    expected to be pointing to a file name within the same directory.
    """
    if os.path.islink(path_to_copy):
        copy_simple_file_name_symlink(path_to_copy, dest_path)
    elif os.path.isfile(path_to_copy):
        log(f"Copying {path_to_copy} to {dest_path}")
        shutil.copy(path_to_copy, dest_path)
    else:
        raise IOError(f"Unknown file type {path_to_copy}, cannot copy it to {dest_path}")
