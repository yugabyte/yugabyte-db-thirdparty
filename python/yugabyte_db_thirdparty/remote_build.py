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
    log_and_run_cmd,
    PushDir,
    YB_THIRDPARTY_DIR,
)


def build_remotely(remote_server: str, remote_build_code_path: str) -> None:
    assert remote_server is not None
    assert remote_build_code_path is not None
    assert remote_build_code_path.startswith('/')

    def run_ssh_cmd(ssh_args: List[str]) -> None:
        log_and_run_cmd(['ssh', remote_server] + ssh_args)

    quoted_remote_path = shlex.quote(remote_build_code_path)

    with PushDir(YB_THIRDPARTY_DIR):
        excluded_files_str = subprocess.check_output(
            ['git', '-C', '.', 'ls-files', '--exclude-standard', '-oi', '--directory'])
        assert os.path.isdir('.git')
        excluded_files_path = os.path.join(os.getcwd(), '.git', 'ignores.tmp')
        with open(excluded_files_path, 'wb') as excluded_files_file:
            excluded_files_file.write(excluded_files_str)

        log_and_run_cmd([
            'rsync',
            '-avh',
            '--delete',
            '--exclude', '.git',
            '--exclude-from=%s' % excluded_files_path,
            '.',
            '%s:%s' % (remote_server, remote_build_code_path)])

        remote_bash_script = 'cd %s && ./build_thirdparty.sh %s' % (
            quoted_remote_path,
            ' '.join(shlex.quote(arg) for arg in sys.argv[1:])
        )
        # TODO: why exactly do we need shlex.quote here?
        run_ssh_cmd(['bash', '-c', shlex.quote(remote_bash_script.strip())])
