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
Allows debugging the yugabyte-db-thirdparty Python codebase by syncing local changes to a remote
server and running it there.
"""

import subprocess
import shlex
import os
import sys

from typing import List

from yugabyte_db_thirdparty.util import (
    log,
    log_and_run_cmd,
    log_and_get_cmd_output,
    PushDir,
    YB_THIRDPARTY_DIR,
)
from yugabyte_db_thirdparty.util import split_into_word_set


def build_remotely(remote_server: str, remote_build_code_path: str) -> None:
    assert remote_server is not None
    assert remote_build_code_path is not None
    assert remote_build_code_path.startswith('/')

    def run_ssh_cmd(ssh_args: List[str]) -> None:
        log_and_run_cmd(['ssh', remote_server] + ssh_args)

    def run_remote_bash_script(bash_script: str) -> None:
        bash_script = bash_script.strip()
        log("Running bash script remotely: %s", bash_script)
        # TODO: why exactly do we need shlex.quote here?
        run_ssh_cmd(['bash', '-c', shlex.quote(bash_script)])

    def get_ssh_cmd_output(ssh_args: List[str]) -> None:
        log_and_get_cmd_output(['ssh', remote_server] + ssh_args)

    quoted_remote_path = shlex.quote(remote_build_code_path)
    # Ensure the remote directory exists.
    run_remote_bash_script('[[ -d %s ]]' % quoted_remote_path)

    with PushDir(YB_THIRDPARTY_DIR):
        excluded_files_str = subprocess.check_output(
            ['git', '-C', '.', 'ls-files', '--exclude-standard', '-oi', '--directory'])
        assert os.path.isdir('.git')
        excluded_files_path = os.path.join(os.getcwd(), '.git', 'ignores.tmp')
        with open(excluded_files_path, 'wb') as excluded_files_file:
            excluded_files_file.write(excluded_files_str)

        exclude_args: List[str] = []
        exclude_patterns = ['.git']
        for exclude_pattern in exclude_patterns:
            exclude_args.append('--exclude')
            exclude_args.append(exclude_pattern)

        log_and_run_cmd(
            ['rsync', '-avh', '--delete'] + exclude_args + [
                '--exclude-from=%s' % excluded_files_path,
                '.',
                '%s:%s' % (remote_server, remote_build_code_path)
            ]
        )

        remote_bash_script = 'cd %s && ./build_thirdparty.sh %s' % (
            quoted_remote_path, shlex.join(sys.argv[1:])
        )

        run_remote_bash_script(remote_bash_script)
