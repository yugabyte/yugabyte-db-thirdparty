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
import re
import shutil
import subprocess
import time

from typing import Optional, List, Dict, cast, TYPE_CHECKING
from urllib.parse import urlparse

from yugabyte_db_thirdparty.archive_handling import ARCHIVE_TYPES
from yugabyte_db_thirdparty.archive_handling import split_archive_file_name
from yugabyte_db_thirdparty.checksums import (
    get_checksum_file_path, CHECKSUM_SUFFIX)
from yugabyte_db_thirdparty.custom_logging import log, fatal
from yugabyte_db_thirdparty.dependency import Dependency
from yugabyte_db_thirdparty.string_util import shlex_join
from yugabyte_db_thirdparty.util import (
    PushDir,
    compute_file_sha256,
    remove_path,
    YB_THIRDPARTY_DIR,
    which_must_exist,
    get_temporal_randomized_file_name_suffix,
    read_file
)
from yugabyte_db_thirdparty.file_util import mkdir_p
from yugabyte_db_thirdparty.constants import ADD_CHECKSUM_ARG


MAX_FETCH_ATTEMPTS = 20
MAX_REDOWNLOAD_ATTEMPTS_AFTER_WRONG_CHECKSUM = 3
INITIAL_DOWNLOAD_RETRY_SLEEP_TIME_SEC = 1.0
DOWNLOAD_RETRY_SLEEP_INCREASE_SEC = 0.5
ALTERNATIVE_URL_PREFIX = 'https://downloads.yugabyte.com/yugabyte-db-thirdparty/'


def is_downloaded_file_not_found(downloaded_file_path: str) -> bool:
    if not os.path.exists(downloaded_file_path):
        return False
    with open(downloaded_file_path, 'rb') as input_file:
        byte_array = input_file.read(14)
    return byte_array == b'404: Not Found'


class DownloadManager:
    should_add_checksum: bool
    download_dir: str
    file_name_to_checksum: Dict[str, str]
    checksum_file_path: str
    curl_path: str

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
            out_dir, 'tmp-extract-%s-%s' % (
                os.path.basename(archive_file_name),
                get_temporal_randomized_file_name_suffix()
            ))
        if os.path.exists(tmp_out_dir):
            raise IOError("Just-generated unique directory name already exists: %s" % tmp_out_dir)
        os.makedirs(tmp_out_dir)
        assert os.path.isdir(tmp_out_dir), f"Failed to create directory {tmp_out_dir}"

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

        self.file_name_to_checksum = {}
        with open(self.checksum_file_path, 'rt') as inp:
            for line in inp:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                sum, fname = line.split(None, 1)
                if not re.match('^[0-9a-f]{64}$', sum):
                    fatal("Invalid checksum: '%s' for archive name: '%s' in %s. Expected to be a "
                          "SHA-256 sum (64 hex characters).", sum, fname, self.checksum_file_path)
                self.file_name_to_checksum[fname] = sum

    def get_expected_checksum(self, file_name: str) -> str:
        checksum = self.get_expected_checksum_and_maybe_add_to_file(
            file_name=file_name,
            downloaded_path=None)
        if checksum is None:
            raise ValueError(f"No expected checksum found for file name {file_name}")
        return checksum

    def get_expected_checksum_and_maybe_add_to_file(
            self,
            file_name: str,
            downloaded_path: Optional[str]) -> Optional[str]:
        if file_name not in self.file_name_to_checksum:
            if self.should_add_checksum and downloaded_path:
                with open(self.checksum_file_path, 'rt') as inp:
                    lines = inp.readlines()
                lines = [line.rstrip() for line in lines]
                checksum = compute_file_sha256(downloaded_path)
                lines.append("%s  %s" % (checksum, file_name))
                with open(self.checksum_file_path, 'wt') as out:
                    for line in lines:
                        out.write(line + "\n")
                self.file_name_to_checksum[file_name] = checksum
                log("Added checksum for %s to %s: %s", file_name, self.checksum_file_path, checksum)
                return checksum

            return None
        return self.file_name_to_checksum[file_name]

    def verify_checksum(self, file_name: str, expected_checksum: Optional[str]) -> bool:
        real_checksum = compute_file_sha256(file_name)
        file_basename = os.path.basename(file_name)
        if expected_checksum is None:
            fatal(
                f"No expected checksum provided for file '{file_basename}'. Consider adding the "
                f"following line to thirdparty_src_checksums.txt (or re-run with "
                f"{ADD_CHECKSUM_ARG}):\n"
                f"{real_checksum}  {file_basename}\n"
            )
        return real_checksum == expected_checksum

    def ensure_file_downloaded(
            self,
            url: str,
            file_path: str,
            enable_using_alternative_url: bool,
            expected_checksum: Optional[str] = None,
            verify_checksum: bool = True) -> None:
        log(f"Ensuring {url} is downloaded to path {file_path}")
        file_name = os.path.basename(file_path)

        mkdir_p(self.download_dir)

        if os.path.exists(file_path) and verify_checksum:
            # We check the file name against our checksum map only if the file exists. This is done
            # so that we would still download the file even if we don't know the checksum, making it
            # easier to add new third-party dependencies.
            if expected_checksum is None:
                expected_checksum = self.get_expected_checksum_and_maybe_add_to_file(
                    file_name, downloaded_path=file_path)
            if self.verify_checksum(file_path, expected_checksum):
                log("No need to re-download %s: checksum already correct", file_name)
                return
            log("File %s already exists but has wrong checksum, removing", file_path)
            remove_path(file_path)

        log("Fetching %s from %s", file_name, url)

        download_successful = False
        alternative_url = ALTERNATIVE_URL_PREFIX + file_name
        total_attempts = 0

        url_candidates = [url]
        if enable_using_alternative_url:
            url_candidates += [alternative_url]

        for effective_url in url_candidates:
            if effective_url == alternative_url:
                log("Switching to alternative download URL %s after %d attempts",
                    alternative_url, total_attempts)
            sleep_time_sec = INITIAL_DOWNLOAD_RETRY_SLEEP_TIME_SEC
            for attempt_index in range(1, MAX_FETCH_ATTEMPTS + 1):
                try:
                    total_attempts += 1
                    curl_cmd_line = [
                        self.curl_path,
                        '-o',
                        file_path,
                        '-L',  # follow redirects
                        '--silent',
                        '--show-error',
                        '--location',
                        effective_url]
                    log("Running command: %s", shlex_join(curl_cmd_line))
                    subprocess.check_call(curl_cmd_line)

                    if is_downloaded_file_not_found(file_path):
                        os.remove(file_path)
                        raise ValueError(f"Could not download {self.curl_path}: not found")

                    if verify_checksum:
                        if expected_checksum is None:
                            expected_checksum = self.get_expected_checksum_and_maybe_add_to_file(
                                file_name, downloaded_path=file_path)
                        if not self.verify_checksum(file_path, expected_checksum):
                            error_msg = (
                                "File '%s' has wrong checksum after downloading from '%s'. "
                                "Has %s, but expected: %s." % (
                                    file_path,
                                    url,
                                    compute_file_sha256(file_path),
                                    expected_checksum))
                            if attempt_index <= MAX_REDOWNLOAD_ATTEMPTS_AFTER_WRONG_CHECKSUM:
                                error_msg += " Will delete and re-download."
                                remove_path(file_path)
                                log(error_msg)
                                continue
                            else:
                                raise IOError(error_msg + ("Attempt: %d" % attempt_index))

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

        if not download_successful:
            fatal("Failed to download URL %s", url)
        if not os.path.exists(file_path):
            fatal("Downloaded '%s' but but unable to find '%s'", url, file_path)

    def download_dependency(
            self,
            dep: Dependency,
            src_path: str,
            archive_path: Optional[str]) -> None:
        patch_marker_file_path = os.path.join(
                src_path, 'patchmarker-version{}-{}patches'.format(
                    dep.patch_version, len(dep.patches)))
        log("Patch marker file: %s", patch_marker_file_path)
        if os.path.exists(patch_marker_file_path) and not dep.local_archive:
            log("Patch marker file %s already exists, skipping download", patch_marker_file_path)
            return

        remove_path(src_path)

        if dep.mkdir_only:
            # Just create an empty directory with the specified name.
            log("Creating %s", src_path)
            mkdir_p(src_path)
        elif dep.local_archive:
            log("Copying from local archive at %s to %s", dep.local_archive, src_path)
            shutil.rmtree(src_path, ignore_errors=True)
            shutil.copytree(dep.local_archive, src_path)
        else:
            download_url = dep.download_url
            log("Download URL: %s", download_url)
            assert download_url is not None, \
                   "Download URL not specified for dependency %s" % dep.name

            if archive_path is None:
                log("archive_path is not set, skipping download")
                return
            self.ensure_file_downloaded(
                url=download_url,
                file_path=archive_path,
                enable_using_alternative_url=True)
            self.extract_archive(archive_path,
                                 os.path.dirname(src_path),
                                 os.path.basename(src_path))

        if hasattr(dep, 'extra_downloads'):
            for extra in dep.extra_downloads:
                assert extra.archive_name is not None
                archive_path = os.path.join(self.download_dir, extra.archive_name)
                log("Downloading %s from %s", extra.archive_name, extra.download_url)
                self.ensure_file_downloaded(
                    url=extra.download_url,
                    file_path=archive_path,
                    enable_using_alternative_url=True)
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
                    log("Running command: patch -p{}".format(dep.patch_strip))
                    process = subprocess.Popen(['patch', '-p{}'.format(dep.patch_strip)],
                                               stdin=subprocess.PIPE)
                    with open(os.path.join(YB_THIRDPARTY_DIR, 'patches', patch), 'rt', newline="") as inp:
                        patch = inp.read()
                    assert process.stdin is not None
                    log(patch.encode('utf-8'))
                    process.stdin.write(patch.encode('utf-8'))
                    process.stdin.close()
                    exit_code = process.wait()
                    if exit_code:
                        fatal("Patch {} failed with code: {}".format(dep.name, exit_code))
                if dep.post_patch:
                    subprocess.check_call(dep.post_patch)

        with open(patch_marker_file_path, 'wb') as out:
            # Just create an empty file.
            pass

    def download_toolchain(
            self,
            toolchain_url: str,
            dest_parent_dir: str) -> str:
        """
        Download a C/C++ compiler toolchain, e.g. Linuxbrew GCC 5.5, or LLVM. Returns the directory
        where the toolchain is installed.
        """
        parsed_url = urlparse(toolchain_url)
        file_name = os.path.basename(parsed_url.path)

        dest_dir_name, archive_extension = split_archive_file_name(file_name)
        assert archive_extension.startswith('.'), \
            "Expected the archive extension to start with a dot, got: '%s'. URL: %s" % (
                toolchain_url, archive_extension
            )

        toolchain_dest_dir_path = os.path.join(dest_parent_dir, dest_dir_name)
        if os.path.exists(toolchain_dest_dir_path):
            log(f"Toolchain directory '{toolchain_dest_dir_path}' already exists, not downloading "
                f"URL {toolchain_url}")
            return toolchain_dest_dir_path

        mkdir_p(dest_parent_dir)

        tmp_suffix = ".tmp-%s" % get_temporal_randomized_file_name_suffix()

        archive_temporary_dest_path = os.path.join(
            dest_parent_dir,
            "".join([
                dest_dir_name,
                tmp_suffix,
                archive_extension
            ])
        )
        archive_temporary_dest_checksum_path = archive_temporary_dest_path + CHECKSUM_SUFFIX

        try:
            self.ensure_file_downloaded(
                toolchain_url + CHECKSUM_SUFFIX,
                archive_temporary_dest_checksum_path,
                enable_using_alternative_url=False,
                verify_checksum=False)
            with open(archive_temporary_dest_checksum_path) as checksum_file:
                expected_checksum = checksum_file.read().strip().split()[0]

            self.ensure_file_downloaded(
                toolchain_url,
                archive_temporary_dest_path,
                enable_using_alternative_url=False,
                expected_checksum=expected_checksum)

            if dest_dir_name.startswith('linuxbrew'):
                dest_dir_name_tmp = dest_dir_name + tmp_suffix
                self.extract_archive(
                    archive_file_name=archive_temporary_dest_path,
                    out_dir=dest_parent_dir,
                    out_name=dest_dir_name_tmp
                )
                orig_brew_home = read_file(
                    os.path.join(dest_parent_dir, dest_dir_name_tmp, 'ORIG_BREW_HOME')
                ).strip()
                os.rename(os.path.join(dest_parent_dir, dest_dir_name_tmp), orig_brew_home)
                os.symlink(os.path.basename(orig_brew_home), toolchain_dest_dir_path)
            else:
                self.extract_archive(
                    archive_file_name=archive_temporary_dest_path,
                    out_dir=dest_parent_dir,
                    out_name=dest_dir_name
                )

            if not os.path.isdir(toolchain_dest_dir_path):
                raise RuntimeError(
                    f"Extracting the archive downloaded from {toolchain_url} did not create "
                    f"directory '{toolchain_dest_dir_path}'.")

        finally:
            for path_to_remove in [
                archive_temporary_dest_path,
                archive_temporary_dest_checksum_path
            ]:
                if os.path.exists(path_to_remove):
                    log("Removing temporary file '%s'", path_to_remove)
                    os.remove(path_to_remove)
        return toolchain_dest_dir_path
