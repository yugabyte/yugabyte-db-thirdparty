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
import hashlib
import shutil
import subprocess
import datetime
import random
import subprocess
import logging

from yugabyte_db_thirdparty.custom_logging import log, fatal
from yugabyte_db_thirdparty.string_util import normalize_cmd_args, shlex_join

from typing import List, Optional, Any, Dict, Set


SHARED_LIBRARY_EXTENSIONS = ['so', 'dylib']


def _detect_yb_thirdparty_dir() -> str:
    yb_thirdparty_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if not os.path.isdir(os.path.join(yb_thirdparty_dir, 'python', 'yugabyte_db_thirdparty')):
        raise IOError("Could not identify correct third-party directory, got %s" %
                      yb_thirdparty_dir)
    return yb_thirdparty_dir


YB_THIRDPARTY_DIR = _detect_yb_thirdparty_dir()


def assert_list_contains(items: List[str], required_item: str) -> None:
    """
    >>> assert_list_contains(['a', 'b', 'c'], 'a')
    >>> assert_list_contains(['a', 'b', 'c'], 'x')
    Traceback (most recent call last):
    ValueError: x not found in ['a', 'b', 'c']
    """
    if required_item not in items:
        raise ValueError("%s not found in %s" % (required_item, items))


def assert_dir_exists(dir_path: str) -> None:
    assert os.path.isdir(dir_path), "Directory does not exist or is not a directory: %s" % dir_path


def compute_file_hash(hash: Any, filename: str, block_size: int = 65536) -> str:
    """
    Compute the hash sun of a file by updating the existing hash object.
    """
    # TODO: use a more precise argument type for hash.
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            hash.update(block)
    return hash.hexdigest()


def compute_file_sha256(path: str) -> str:
    return compute_file_hash(hashlib.sha256(), path)


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
        assert path != '/'
        # shutil.rmtree is very slow compared to rm -rf.
        subprocess.check_call(['rm', '-rf', path])
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


def dict_set_or_del(d: Any, k: Any, v: Any) -> None:
    """
    Set the value of the given key in a dictionary to the given value, or delete it if the value
    is None.
    """
    if v is None:
        if k in d:
            del d[k]
    else:
        d[k] = v


class EnvVarContext:
    """
    Sets the given environment variables and restores them on exit. A None value means the variable
    is undefined.
    """

    env_vars: Dict[str, Optional[str]]
    saved_env_vars: Dict[str, Optional[str]]

    def __init__(self, **env_vars: Any) -> None:
        self.env_vars = env_vars

    def __enter__(self) -> None:
        self.saved_env_vars = {}
        for env_var_name, new_value in self.env_vars.items():
            self.saved_env_vars[env_var_name] = os.environ.get(env_var_name)
            dict_set_or_del(os.environ, env_var_name, new_value)

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        for env_var_name, saved_value in self.saved_env_vars.items():
            dict_set_or_del(os.environ, env_var_name, saved_value)


def read_file(file_path: str) -> str:
    with open(file_path) as input_file:
        return input_file.read()


def write_file(file_path: str, data: str) -> None:
    with open(file_path, 'w') as output_file:
        output_file.write(data)


def add_path_entry(new_path_entry: str) -> None:
    """
    Adds a new PATH entry in front of the PATH environment variable, if the new directory is not
    already present in PATH.
    """
    path_str = (os.getenv('PATH') or '').strip()
    if not path_str:
        # Should not really happen but let's handle it.
        os.environ['PATH'] = new_path_entry
        return

    existing_path_entries = path_str.split(':')
    if new_path_entry not in existing_path_entries:
        os.environ['PATH'] = ':'.join([new_path_entry] + existing_path_entries)


def _log_cmd_to_run(args: List[str], cwd: Optional[Any]) -> None:
    cwd = cwd or os.getcwd()
    log("Running command: %s (in directory: %s)", shlex_join(args), cwd)


def log_and_run_cmd(args: List[Any], **kwargs: Any) -> None:
    args = normalize_cmd_args(args)
    _log_cmd_to_run(args, cwd=kwargs.get('cwd'))
    subprocess.check_call(args, **kwargs)


def log_and_run_cmd_ignore_errors(args: List[Any], **kwargs: Any) -> None:
    args = normalize_cmd_args(args)
    args_str = shlex_join(args)
    _log_cmd_to_run(args, cwd=kwargs.get('cwd'))
    try:
        subprocess.check_call(args, **kwargs)
    except subprocess.CalledProcessError as ex:
        logging.exception("Command failed: %s (ignoring the error)", args_str, ex)


def log_and_get_cmd_output(args: List[Any], **kwargs: Any) -> str:
    args = normalize_cmd_args(args)
    _log_cmd_to_run(args, cwd=kwargs.get('cwd'))
    cmd_result = subprocess.check_output(args, **kwargs)
    # The pyright type checker erroneously thinks that the type of cmd_result is str.
    assert isinstance(cmd_result, bytes)
    return cmd_result.decode('utf-8')


def get_seconds_timestamp_for_file_name() -> str:
    """
    Returns the current timestamp at a second-level granularity in a format suitable for inclusion
    in file and directory names.
    """
    return datetime.datetime.now().strftime('%Y-%m-%dT%H_%M_%S')


def get_random_suffix_for_file_name() -> str:
    """
    Returns a random 9-digit integer.

    >>> len(get_random_suffix_for_file_name())
    9
    """
    return str(random.randint(10 ** 8, 10 ** 9 - 1))


def get_temporal_randomized_file_name_suffix() -> str:
    return "%s-%s" % (
        get_seconds_timestamp_for_file_name(),
        get_random_suffix_for_file_name()
    )


def create_symlink_and_log(link_to: str, symlink_path: str) -> None:
    log(f"Creating symlink {symlink_path} -> {link_to}")
    os.symlink(link_to, symlink_path)


def create_symlink(src: str, dst: str, src_must_exist: bool = False) -> None:
    """
    Creates a symlink dst pointing to src. Does nothing if the symlink already exists and points
    to the same location.
    """
    if src_must_exist and not os.path.exists(src):
        raise IOError(f"Trying to create a symlink to '{src}' but that location does not exist")

    if os.path.exists(dst):
        if os.path.islink(dst):
            current_target = os.readlink(dst)
            if current_target == src:
                return
            raise IOError(f"Symbolic link '{dst}' already exists and does not point to '{src}'.")
        else:
            raise IOError(f"File already exists and is not a symlink: '{dst}'")
    create_symlink_and_log(src, dst)


def extract_major_version(version_str: str) -> int:
    '''
    >>> extract_major_version('2.3.4')
    2
    '''
    return int(version_str.split('.')[0])


def is_shared_library_name(name: str) -> bool:
    '''
    >>> is_shared_library_name('libfoo.so')
    True
    >>> is_shared_library_name('libfoo.dylib')
    True
    >>> is_shared_library_name('libfoo.so.1')
    True
    >>> is_shared_library_name('libfoo.dylib.1')
    True
    >>> is_shared_library_name('soawesome.o')
    False
    >>> is_shared_library_name('dylibawesome.o')
    False
    '''
    return any([
        name.endswith('.' + ext) or '.%s.' % ext in name for ext in SHARED_LIBRARY_EXTENSIONS
    ])


class UnexpectedExitCodeError(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)


def capture_all_output(
        args: List[str],
        allowed_exit_codes: Set[int],
        env: Dict[str, str]) -> List[str]:
    '''
    Runs the given command represented by a list of arguments, and captures all output (stdout
    and stderr) as a list of lines.

    :param args: Command line to run..
    :param allowed_exit_codes: The list of allowed exit codes for which there would be no error.
                               Also, 0 is always implicitly included
    :param env: Additional environment variables for the child process.
    :raises: UnexpectedExitCodeError in case the exit code is not 0 or one of the allowed exit
             codes.
    '''
    try:
        out_bytes = subprocess.check_output(args, stderr=subprocess.STDOUT, env=env)
    except subprocess.CalledProcessError as ex:
        if ex.returncode not in allowed_exit_codes:
            error_msg = f"Unexpected exit code {ex.returncode} from: {shlex_join(args)} " \
                        f"(expected one of { set(sorted(allowed_exit_codes | {0})) })"
            log(error_msg)
            raise UnexpectedExitCodeError(error_msg)
        out_bytes = ex.stdout
    return out_bytes.decode('utf-8').splitlines()