from yugabyte_db_thirdparty.git_util import get_git_sha1
from yugabyte_db_thirdparty.util import YB_THIRDPARTY_DIR, log_and_run_cmd, compute_file_sha256

import os
import logging
import subprocess
import time


EXCLUDE_PATTERNS_RELATIVE_TO_ARCHIVE_ROOT = [
    '.git',
    'src',
    'build',
    'venv',
    'download',
    # TODO: figure out what generates this file.
    'a.out'
]

GENERAL_EXCLUDE_PATTERNS = ['*.pyc', '*.o']

MAX_UPLOAD_ATTEMPTS = 20


class Packager:
    build_dir_parent: str
    archive_dir_name: str
    archive_tarball_name: str
    archive_tarball_path: str
    archive_sha256_path: str
    git_sha1: str

    def __init__(self) -> None:
        self.build_dir_parent = os.path.dirname(YB_THIRDPARTY_DIR)
        self.archive_dir_name = os.path.basename(YB_THIRDPARTY_DIR)
        self.archive_tarball_name = self.archive_dir_name + '.tar.gz'
        self.archive_tarball_path = os.path.join(self.build_dir_parent, self.archive_tarball_name)
        self.archive_sha256_path = self.archive_tarball_path + '.sha256'
        self.git_sha1 = get_git_sha1(YB_THIRDPARTY_DIR)

    def create_package(self) -> None:
        if os.path.exists(self.archive_tarball_path):
            logging.info("File already exists, deleting: %s", self.archive_tarball_path)
            os.remove(self.archive_tarball_path)

        tar_cmd = ['tar']
        for excluded_pattern in EXCLUDE_PATTERNS_RELATIVE_TO_ARCHIVE_ROOT:
            tar_cmd.extend([
                '--exclude',
                '%s/%s' % (self.archive_dir_name, excluded_pattern)
            ])
        for excluded_pattern in GENERAL_EXCLUDE_PATTERNS:
            tar_cmd.extend(['--exclude', excluded_pattern])

        tar_cmd.extend(['-czf', self.archive_tarball_path, self.archive_dir_name])
        log_and_run_cmd(tar_cmd, cwd=self.build_dir_parent)

        sha256 = compute_file_sha256(self.archive_tarball_path)
        with open(self.archive_sha256_path, 'w') as sha256_file:
            sha256_file.write('%s  %s\n' % (sha256, self.archive_tarball_name))
        logging.info(
            "Archive SHA256 checksum: %s, created checksum file: %s",
            sha256, self.archive_sha256_path)

    def upload_package(self, tag: str) -> None:
        hub_cmd = [
            'hub', 'release', 'create', tag,
            '-m', 'Release %s' % tag,
            '-a', self.archive_tarball_path,
            '-a', self.archive_sha256_path,
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
