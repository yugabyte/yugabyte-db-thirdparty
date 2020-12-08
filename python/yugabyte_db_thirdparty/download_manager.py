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
import random
import subprocess
import shutil
import re
import time

from datetime import datetime
from typing import Optional, List, cast

from yugabyte_db_thirdparty.custom_logging import log, fatal
from yugabyte_db_thirdparty.dependency import Dependency
from yugabyte_db_thirdparty.archive_handling import ARCHIVE_TYPES
from yugabyte_db_thirdparty.checksums import get_checksum_file_path
from yugabyte_db_thirdparty.util import (
    PushDir,
    compute_file_sha256,
    mkdir_if_missing,
    remove_path,
    YB_THIRDPARTY_DIR,
    which_must_exist,
)
from yugabyte_db_thirdparty.string_util import shlex_join

MAX_FETCH_ATTEMPTS = 20
INITIAL_DOWNLOAD_RETRY_SLEEP_TIME_SEC = 1.0
DOWNLOAD_RETRY_SLEEP_INCREASE_SEC = 0.5
ALTERNATIVE_URL_PREFIX = 'https://downloads.yugabyte.com/yugabyte-db-thirdparty/'


class DownloadManager:
    def __init__(
            self,
            should_add_checksum: bool,
            download_dir: str) -> None:
        self.should_add_checksum = should_add_checksum
        self.download_dir = download_dir
        self.checksum_file_path = get_checksum_file_path()

        # TODO: do not use curl for downloads. Use a Python HTTP library.
        self.curl_path = which_must_exist('curl')

        self.load_expected_checksums()

    def extract_archive(
            self,
            archive_file_name: str,
            out_dir: str,
            out_name: Optional[str] = None) -> None:
        """
        Extract the given archive into a subdirectory of out_dir, optionally renaming it to
        the specified name out_name. The archive is expected to contain exactly one directory.
        If out_name is not specified, the name of the directory inside the archive becomes
        the name of the destination directory.

        out_dir is the parent directory that should contain the extracted directory when the
        function returns.
        """

        def dest_dir_already_exists(full_out_path: str) -> bool:
            if os.path.exists(full_out_path):
                log("Directory already exists: %s, skipping extracting %s" % (
                        full_out_path, archive_file_name))
                return True
            return False

        full_out_path = None
        if out_name:
            full_out_path = os.path.join(out_dir, out_name)
            if dest_dir_already_exists(full_out_path):
                return

        # Extract the archive into a temporary directory.
        tmp_out_dir = os.path.join(
            out_dir, 'tmp-extract-%s-%s-%d' % (
                os.path.basename(archive_file_name),
                datetime.now().strftime('%Y-%m-%dT%H_%M_%S'),  # Current second-level timestamp.
                random.randint(10 ** 8, 10 ** 9 - 1)))  # A random 9-digit integer.
        if os.path.exists(tmp_out_dir):
            raise IOError("Just-generated unique directory name already exists: %s" % tmp_out_dir)
        os.makedirs(tmp_out_dir)

        archive_extension = None
        for ext in ARCHIVE_TYPES:
            if archive_file_name.endswith(ext):
                archive_extension = ext
                break
        if not archive_extension:
            fatal("Unknown archive type for: {}".format(archive_file_name))
        assert archive_extension is not None

        try:
            with PushDir(tmp_out_dir):
                cmd = ARCHIVE_TYPES[archive_extension].format(archive_file_name)
                log("Extracting %s in temporary directory %s", cmd, tmp_out_dir)
                subprocess.check_call(cmd, shell=True)
                extracted_subdirs = [
                    subdir_name for subdir_name in os.listdir(tmp_out_dir)
                    if not subdir_name.startswith('.')
                ]
                if len(extracted_subdirs) != 1:
                    raise IOError(
                        "Expected the extracted archive %s to contain exactly one "
                        "subdirectory and no files, found: %s" % (
                            archive_file_name, extracted_subdirs))
                extracted_subdir_basename = extracted_subdirs[0]
                extracted_subdir_path = os.path.join(tmp_out_dir, extracted_subdir_basename)
                if not os.path.isdir(extracted_subdir_path):
                    raise IOError(
                        "This is a file, expected it to be a directory: %s" %
                        extracted_subdir_path)

                if not full_out_path:
                    full_out_path = os.path.join(out_dir, extracted_subdir_basename)
                    if dest_dir_already_exists(full_out_path):
                        return

                log("Moving %s to %s", extracted_subdir_path, full_out_path)
                shutil.move(extracted_subdir_path, full_out_path)
        finally:
            log("Removing temporary directory: %s", tmp_out_dir)
            shutil.rmtree(tmp_out_dir)

    def load_expected_checksums(self) -> None:
        if not os.path.exists(self.checksum_file_path):
            fatal("Expected checksum file not found at %s", self.checksum_file_path)

        self.filename2checksum = {}
        with open(self.checksum_file_path, 'rt') as inp:
            for line in inp:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                sum, fname = line.split(None, 1)
                if not re.match('^[0-9a-f]{64}$', sum):
                    fatal("Invalid checksum: '%s' for archive name: '%s' in %s. Expected to be a "
                          "SHA-256 sum (64 hex characters).", sum, fname, self.checksum_file_path)
                self.filename2checksum[fname] = sum

    def get_expected_checksum(self, filename: str, downloaded_path: str) -> str:
        if filename not in self.filename2checksum:
            if self.should_add_checksum:
                with open(self.checksum_file_path, 'rt') as inp:
                    lines = inp.readlines()
                lines = [line.rstrip() for line in lines]
                checksum = compute_file_sha256(downloaded_path)
                lines.append("%s  %s" % (checksum, filename))
                with open(self.checksum_file_path, 'wt') as out:
                    for line in lines:
                        out.write(line + "\n")
                self.filename2checksum[filename] = checksum
                log("Added checksum for %s to %s: %s", filename, self.checksum_file_path, checksum)
                return checksum

            fatal("No expected checksum provided for {}".format(filename))
        return self.filename2checksum[filename]

    def verify_checksum(self, file_name: str, expected_checksum: str) -> bool:
        real_checksum = compute_file_sha256(file_name)
        return real_checksum == expected_checksum

    def ensure_file_downloaded(self, url: str, path: str) -> None:
        log(f"Ensuring {url} is downloaded to path {path}")
        file_name = os.path.basename(path)

        mkdir_if_missing(self.download_dir)

        if os.path.exists(path):
            # We check the filename against our checksum map only if the file exists. This is done
            # so that we would still download the file even if we don't know the checksum, making it
            # easier to add new third-party dependencies.
            expected_checksum = self.get_expected_checksum(file_name, downloaded_path=path)
            if self.verify_checksum(path, expected_checksum):
                log("No need to re-download %s: checksum already correct", file_name)
                return
            log("File %s already exists but has wrong checksum, removing", path)
            remove_path(path)

        log("Fetching %s from %s", file_name, url)

        download_successful = False
        alternative_url = ALTERNATIVE_URL_PREFIX + file_name
        total_attempts = 0
        for effective_url in [url, alternative_url]:
            if effective_url == alternative_url:
                log("Switching to alternative download URL %s after %d attempts",
                    alternative_url, total_attempts)
            sleep_time_sec = INITIAL_DOWNLOAD_RETRY_SLEEP_TIME_SEC
            for attempt_index in range(1, MAX_FETCH_ATTEMPTS + 1):
                try:
                    total_attempts += 1
                    curl_cmd_line = [
                        self.curl_path, '-o', path,
                        '-L',  # follow redirects
                        '--silent',
                        '--show-error',
                        '--location',
                        effective_url]
                    log("Running command: %s", shlex_join(curl_cmd_line))
                    subprocess.check_call(curl_cmd_line)
                    download_successful = True
                    break
                except subprocess.CalledProcessError as ex:
                    log("Error downloading %s (attempt %d for this URL, total attempts %d): %s",
                        self.curl_path, attempt_index, total_attempts, str(ex))
                    if attempt_index == MAX_FETCH_ATTEMPTS and effective_url == alternative_url:
                        log("Giving up after %d attempts", MAX_FETCH_ATTEMPTS)
                        raise ex
                    log("Will retry after %.1f seconds", sleep_time_sec)
                    time.sleep(sleep_time_sec)
                    sleep_time_sec += DOWNLOAD_RETRY_SLEEP_INCREASE_SEC

            if download_successful:
                break

        if not os.path.exists(path):
            fatal("Downloaded '%s' but but unable to find '%s'", url, path)
        expected_checksum = self.get_expected_checksum(file_name, downloaded_path=path)
        if not self.verify_checksum(path, expected_checksum):
            fatal("File '%s' has wrong checksum after downloading from '%s'. "
                  "Has %s, but expected: %s",
                  path, url, compute_file_sha256(path), expected_checksum)

    def download_dependency(
            self,
            dep: Dependency,
            src_path: str,
            archive_path: Optional[str]) -> None:
        patch_level_path = os.path.join(src_path, 'patchlevel-{}'.format(dep.patch_version))
        if os.path.exists(patch_level_path):
            return

        download_url = dep.download_url
        assert download_url is not None, "Download URL not specified for dependency %s" % dep.name

        remove_path(src_path)

        # If download_url is "mkdir" then we just create empty directory with specified name.
        if download_url != 'mkdir':
            if archive_path is None:
                return
            self.ensure_file_downloaded(download_url, archive_path)
            self.extract_archive(archive_path,
                                 os.path.dirname(src_path),
                                 os.path.basename(src_path))
        else:
            log("Creating %s", src_path)
            mkdir_if_missing(src_path)

        if hasattr(dep, 'extra_downloads'):
            for extra in dep.extra_downloads:
                assert extra.archive_name is not None
                archive_path = os.path.join(self.download_dir, extra.archive_name)
                log("Downloading %s from %s", extra.archive_name, extra.download_url)
                self.ensure_file_downloaded(extra.download_url, archive_path)
                output_path = os.path.join(src_path, extra.dir_name)
                self.extract_archive(archive_path, output_path)
                if extra.post_exec is not None:
                    with PushDir(output_path):
                        assert isinstance(extra.post_exec, list)
                        if isinstance(extra.post_exec[0], str):
                            subprocess.check_call(cast(List[str], extra.post_exec))
                        else:
                            for command in extra.post_exec:
                                subprocess.check_call(command)

        if hasattr(dep, 'patches'):
            with PushDir(src_path):
                for patch in dep.patches:
                    log("Applying patch: %s", patch)
                    process = subprocess.Popen(['patch', '-p{}'.format(dep.patch_strip)],
                                               stdin=subprocess.PIPE)
                    with open(os.path.join(YB_THIRDPARTY_DIR, 'patches', patch), 'rt') as inp:
                        patch = inp.read()
                    assert process.stdin is not None
                    process.stdin.write(patch.encode('utf-8'))
                    process.stdin.close()
                    exit_code = process.wait()
                    if exit_code:
                        fatal("Patch {} failed with code: {}".format(dep.name, exit_code))
                if dep.post_patch:
                    subprocess.check_call(dep.post_patch)

        with open(patch_level_path, 'wb') as out:
            # Just create an empty file.
            pass
