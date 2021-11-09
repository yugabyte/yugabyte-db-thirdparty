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

import os

from typing import Optional, Tuple


TAR_EXTRACT = 'tar --no-same-owner -xf {}'
# -o -- force overwriting existing files
ZIP_EXTRACT = 'unzip -q -o {}'

ARCHIVE_TYPES = {
    '.tar.bz2': TAR_EXTRACT,
    '.tar.gz': TAR_EXTRACT,
    '.tar.xz': TAR_EXTRACT,
    '.tgz': TAR_EXTRACT,
    '.zip': ZIP_EXTRACT,
}


def make_archive_name(name: str, version: str, download_url: Optional[str]) -> Optional[str]:
    if download_url is None:
        return '{}-{}{}'.format(name, version, '.tar.gz')
    for ext in ARCHIVE_TYPES:
        if download_url.endswith(ext):
            return '{}-{}{}'.format(name, version, ext)
    raise ValueError("Could not determine archive name for URL %s" % download_url)
    return None


def split_archive_file_name(archive_file_name: str) -> Tuple[str, str]:
    """
    Split the extension from the archive name. This is different from os.path.splitext because e.g.
    '.tar.gz' is considered an indivisible extension, while os.path.splitext would only consider
    '.gz' an extension.

    >>> split_archive_file_name('foo.tar.gz')
    ('foo', '.tar.gz')
    >>> split_archive_file_name('foo.tar.bz2')
    ('foo', '.tar.bz2')
    >>> split_archive_file_name('my.archive.zip')
    ('my.archive', '.zip')
    >>> split_archive_file_name('somefile')
    ('somefile', '')
    """
    for archive_extension in ARCHIVE_TYPES:
        if archive_file_name.endswith(archive_extension):
            return (archive_file_name[:-len(archive_extension)],
                    archive_file_name[-len(archive_extension):])

    return os.path.splitext(archive_file_name)
