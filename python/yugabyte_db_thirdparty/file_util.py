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
            print("Created directory %s" % cur_dir)

    return cur_dir