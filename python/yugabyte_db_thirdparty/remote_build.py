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
    shlex_join,
)


def get_current_git_branch_name() -> str:
    return subprocess.check_output(
        shlex.split('git rev-parse --abbrev-ref HEAD')).strip().decode('utf-8')


def rsync_code_to(rsync_dest: str) -> None:
    with PushDir(YB_THIRDPARTY_DIR):
        excluded_files_bytes: bytes = subprocess.check_output(
            ['git', 'ls-files', '--exclude-standard', '-oi', '--directory'])
        assert os.path.isdir('.git')
        excluded_files_path = os.path.join(os.getcwd(), '.git', 'ignores.tmp')
        with open(excluded_files_path, 'wb') as excluded_files_file:
            excluded_files_file.write(excluded_files_bytes)

        rsync_cmd = [
            'rsync',
            '--archive',
            '--verbose',
            '--human-readable',
            '--delete',
            '--checksum',
            '--exclude',
            '.git',
            '--exclude-from=%s' % excluded_files_path, '.', rsync_dest
        ]
        log_and_run_cmd(rsync_cmd)


def copy_code_to(dest_dir: str) -> None:
    parent_dir = os.path.dirname(dest_dir)
    assert os.path.isdir(parent_dir), 'Directory %s does not exist' % parent_dir
    assert not os.path.exists(dest_dir), 'Already exists: %s' % dest_dir
    with PushDir(YB_THIRDPARTY_DIR):
        current_branch_name = get_current_git_branch_name()
        log_and_run_cmd(['git', 'clone', YB_THIRDPARTY_DIR, dest_dir])
        with PushDir(dest_dir):
            log_and_run_cmd(['git', 'checkout', current_branch_name])
        rsync_code_to(dest_dir)


def build_remotely(remote_server: str, remote_build_code_path: str) -> None:
    assert remote_server is not None
    assert remote_build_code_path is not None
    assert remote_build_code_path.startswith('/')

    def run_ssh_cmd(ssh_args: List[str]) -> None:
        log_and_run_cmd(['ssh', remote_server] + ssh_args)

    def run_remote_bash_script(bash_script: str) -> None:
        bash_script = bash_script.strip()
        log("Running script remotely: %s", bash_script)
        # TODO: why exactly do we need shlex.quote here?
        run_ssh_cmd(['bash', '-c', shlex.quote(bash_script)])

    quoted_remote_path = shlex.quote(remote_build_code_path)

    # Ensure the remote directory exists. We are not attempting to create it if it does not.
    run_remote_bash_script('[[ -d %s ]]' % quoted_remote_path)

    with PushDir(YB_THIRDPARTY_DIR):
        local_branch_name = get_current_git_branch_name()

        local_git_remotes = subprocess.check_output(
            shlex.split('git remote -v')).decode('utf-8')

        remote_url = '%s:%s' % (remote_server, remote_build_code_path)
        preferred_remote_name = 'remote-build-%s' % remote_server
        remote_name = None
        for remote_line in local_git_remotes.split('\n'):
            remote_line = remote_line.strip()
            if not remote_line:
                continue
            remote_components = remote_line.split('\t')
            if remote_components[1].endswith(' (push)'):
                parsed_remote_url = remote_components[1][:-7].strip()
                if parsed_remote_url == remote_url:
                    remote_name = remote_components[0]
                    log("Found existing remote %s for %s",
                        remote_name, remote_url)
                    break
        if remote_name is None:
            log_and_run_cmd(['git', 'remote', 'add', preferred_remote_name, remote_url])
            remote_name = preferred_remote_name

        log("Local branch name: %s, checking it out remotely", local_branch_name)
        run_remote_bash_script(f"""
            set -euo pipefail
            cd {quoted_remote_path}
            git reset --hard HEAD
            git clean -df
            git checkout master
        """)

        log_and_run_cmd(
            ['git', 'push', '--force', remote_name,
             '%s:%s' % (local_branch_name, local_branch_name)])

        run_remote_bash_script('cd %s && git checkout %s' % (
            quoted_remote_path, shlex.quote(local_branch_name)))

        rsync_code_to('%s:%s' % (remote_server, remote_build_code_path))
        remote_bash_script = 'cd %s && ./build_thirdparty.sh %s' % (
            quoted_remote_path, shlex_join(sys.argv[1:])
        )

        run_remote_bash_script(remote_bash_script)
