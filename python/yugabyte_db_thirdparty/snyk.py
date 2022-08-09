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
import subprocess

from sys_detection import is_linux

from yugabyte_db_thirdparty.custom_logging import log
from yugabyte_db_thirdparty.file_system_layout import FileSystemLayout
from yugabyte_db_thirdparty.util import log_and_run_cmd


SNYK_DOWNLOAD_URL = 'https://static.snyk.io/cli/latest/snyk-linux'


def run_snyk_scan(fs_layout: FileSystemLayout) -> None:
    """
    Attempts to run a Snyk scan. Throws an exception in case of an error.
    """
    snyk_token = os.environ.get('SNYK_TOKEN', '').strip()
    if not snyk_token:
        log("SNYK_TOKEN is not set, not running Snyk")
        # This is not a failure. E.g. this could be a PR build.
        return

    if not is_linux():
        log("This is not Linux, not running Snyk")
        # Similarly, not a failure.
        return

    log("Running Snyk vulnerability scan.")
    download_dir_path = fs_layout.tp_download_dir
    snyk_binary_path = os.path.join(download_dir_path, 'snyk')

    if os.path.exists(snyk_binary_path):
        log("Snyk binary already exists at %s, not downloading", snyk_binary_path)
    else:
        log_and_run_cmd(['curl', SNYK_DOWNLOAD_URL, '-o', snyk_binary_path])
    os.chmod(snyk_binary_path, 0o755)

    if subprocess.call([snyk_binary_path, 'auth', snyk_token]) != 0:
        raise RuntimeError("Snyk authentication failed. Aborting scan.")

    log_and_run_cmd([snyk_binary_path, 'monitor', fs_layout.tp_src_dir, '--unmanaged'])
