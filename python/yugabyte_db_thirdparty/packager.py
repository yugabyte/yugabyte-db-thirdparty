from yugabyte_db_thirdparty.git_util import get_git_sha1
from yugabyte_db_thirdparty.util import (
    compute_file_sha256,
    create_symlink_and_log,
    log_and_run_cmd,
    remove_path,
    YB_THIRDPARTY_DIR,
)
from yugabyte_db_thirdparty.checksums import CHECKSUM_SUFFIX

import os
import logging
import subprocess
import time


EXCLUDE_PATTERNS_RELATIVE_TO_ARCHIVE_ROOT = [
    '.git',
    'a.out',  # TODO: figure out what generates this file.
    'build',
    'download',
    'src',
    'venv',
]

GENERAL_EXCLUDE_PATTERNS = ['*.pyc', '*.o']

MAX_UPLOAD_ATTEMPTS = 20

ARCHIVE_SUFFIX = '.tar.gz'


class Packager:
    build_dir_parent: str
    archive_dir_name: str
    archive_tarball_name: str
    archive_tarball_path: str
    archive_checksum_path: str
    git_sha1: str

    def __init__(self) -> None:
        self.build_dir_parent = os.path.dirname(YB_THIRDPARTY_DIR)
        self.archive_dir_name = os.path.basename(YB_THIRDPARTY_DIR)
        self.archive_tarball_name = self.archive_dir_name + ARCHIVE_SUFFIX
        self.archive_tarball_path = os.path.join(self.build_dir_parent, self.archive_tarball_name)
        self.archive_checksum_path = self.archive_tarball_path + CHECKSUM_SUFFIX
        self.git_sha1 = get_git_sha1(YB_THIRDPARTY_DIR)

    def create_package(self) -> None:
        if os.path.exists(self.archive_tarball_path):
            logging.info("File already exists, deleting: %s", self.archive_tarball_path)
            os.remove(self.archive_tarball_path)

        # Create a symlink with a constant name so we can copy the file around and use it for
        # creating artifacts for pull request builds.
        archive_symlink_path = os.path.join(YB_THIRDPARTY_DIR, 'archive' + ARCHIVE_SUFFIX)
        archive_checksum_symlink_path = archive_symlink_path + CHECKSUM_SUFFIX

        tar_cmd = ['tar']
        patterns_to_exclude = EXCLUDE_PATTERNS_RELATIVE_TO_ARCHIVE_ROOT + [
            os.path.basename(file_path) for file_path in [
                archive_symlink_path, archive_checksum_symlink_path
            ]
        ]
        for excluded_pattern in patterns_to_exclude:
            tar_cmd.extend([
                '--exclude',
                '%s/%s' % (self.archive_dir_name, excluded_pattern)
            ])
        for excluded_pattern in GENERAL_EXCLUDE_PATTERNS:
            tar_cmd.extend(['--exclude', excluded_pattern])

        tar_cmd.extend(['-czf', self.archive_tarball_path, self.archive_dir_name])
        log_and_run_cmd(tar_cmd, cwd=self.build_dir_parent)

        sha256 = compute_file_sha256(self.archive_tarball_path)
        with open(self.archive_checksum_path, 'w') as sha256_file:
            sha256_file.write('%s  %s\n' % (sha256, self.archive_tarball_name))
        logging.info(
            "Archive SHA256 checksum: %s, created checksum file: %s",
            sha256, self.archive_checksum_path)

        for file_path in [archive_symlink_path, archive_checksum_symlink_path]:
            remove_path(file_path)

        create_symlink_and_log(self.archive_tarball_path, archive_symlink_path)
        create_symlink_and_log(self.archive_checksum_path, archive_checksum_symlink_path)

    def upload_package(self, tag: str) -> None:
        hub_cmd = [
            'hub', 'release', 'create', tag,
            '-m', 'Release %s' % tag,
            '-a', self.archive_tarball_path,
            '-a', self.archive_checksum_path,
            '-t', self.git_sha1
        ]
        delay_sec = 10
        for attempt_index in range(1, MAX_UPLOAD_ATTEMPTS + 1):
            try:
                log_and_run_cmd(hub_cmd, cwd=YB_THIRDPARTY_DIR)
                break
            except subprocess.CalledProcessError as ex:
                if attempt_index == MAX_UPLOAD_ATTEMPTS:
                    raise
                logging.exception(
                    "Failed to upload release (attempt %d out of %d). Waiting for %d sec.",
                    attempt_index, MAX_UPLOAD_ATTEMPTS, delay_sec)
                time.sleep(delay_sec)
                delay_sec += 2
