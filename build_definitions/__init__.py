#
# Copyright (c) YugaByte, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
# in compliance with the License.  You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied.  See the License for the specific language governing permissions and limitations
# under the License.
#

import os
import sys

import importlib
import pkgutil
import platform
import shutil
import subprocess
import traceback


YELLOW_COLOR = "\033[0;33m"
RED_COLOR = "\033[0;31m"
CYAN_COLOR = "\033[0;36m"
NO_COLOR = "\033[0m"
SEPARATOR = "-" * 80


BUILD_GROUP_COMMON = 1
BUILD_GROUP_INSTRUMENTED = 2


# -------------------------------------------------------------------------------------------------
# Build types
# -------------------------------------------------------------------------------------------------

BUILD_TYPE_COMMON = 'common'

# This build type is built with GCC on Linux, unless --custom-clang-prefix is specified.
# In the latter case this is built with Clang and BUILD_TYPE_CLANG_UNINSTRUMENTED is not used.
BUILD_TYPE_UNINSTRUMENTED = 'uninstrumented'

# Clang-based builds with ASAN+UBSAN and TSAN enabled.
BUILD_TYPE_ASAN = 'asan'
BUILD_TYPE_TSAN = 'tsan'

BUILD_TYPE_CLANG_UNINSTRUMENTED = 'clang_uninstrumented'

BUILD_TYPES = [
    BUILD_TYPE_COMMON,
    BUILD_TYPE_UNINSTRUMENTED,
    BUILD_TYPE_CLANG_UNINSTRUMENTED,
    BUILD_TYPE_ASAN,
    BUILD_TYPE_TSAN
]

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


def _args_to_message(*args):
    n_args = len(args)
    if n_args == 0:
        message = ""
    elif n_args == 1:
        message = args[0]
    else:
        message = args[0] % args[1:]
    return message


def fatal(*args):
    log(*args)
    traceback.print_stack()
    sys.exit(1)


def log(*args):
    sys.stderr.write(_args_to_message(*args) + "\n")


def colored_log(color, *args):
    sys.stderr.write(color + _args_to_message(*args) + NO_COLOR + "\n")


def print_line_with_colored_prefix(prefix, line):
    log("%s[%s] %s%s", CYAN_COLOR, prefix, NO_COLOR, line.rstrip())


def log_output(prefix, args, log_cmd=True):
    try:
        print_line_with_colored_prefix(
            prefix, "Running command: {} (current directory: {})".format(
                args, os.getcwd()))
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in process.stdout:
            print_line_with_colored_prefix(prefix, line.decode('utf-8'))

        process.stdout.close()
        exit_code = process.wait()
        if exit_code:
            fatal("Execution failed with code: {}".format(exit_code))
    except OSError as err:
        log("Error when trying to execute command: " + str(args))
        log("PATH is: %s", os.getenv("PATH"))
        raise


def unset_if_set(name):
    if name in os.environ:
        log('Unsetting %s for third-party build (was set to "%s").', name, os.environ[name])
        del os.environ[name]


def log_separator():
    log("")
    log(SEPARATOR)
    log("")


def heading(title):
    log("")
    log(SEPARATOR)
    log(title)
    log(SEPARATOR)
    log("")


def is_mac():
    return platform.system().lower() == 'darwin'


def is_linux():
    return platform.system().lower() == 'linux'


def is_jenkins_user():
    return os.environ['USER'] == "jenkins"


def is_jenkins():
    return 'BUILD_ID' in os.environ and 'JOB_NAME' in os.environ and is_jenkins_user()


def does_file_start_with_string(file_path: str, s: str) -> bool:
    if not os.path.exists(file_path):
        return False
    with open(file_path) as f:
        return f.read().strip().startswith(s)


IS_UBUNTU = does_file_start_with_string('/etc/issue', 'Ubuntu')
IS_CENTOS = does_file_start_with_string('/etc/centos-release', 'CentOS')


def is_ubuntu():
    return IS_UBUNTU


def is_centos():
    return IS_CENTOS


def remove_path(path):
    if not os.path.exists(path):
        return
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def mkdir_if_missing(path):
    if os.path.exists(path):
        if not os.path.isdir(path):
            fatal("Trying to create dir {}, but file with the same path already exists"
                  .format(path))
        return
    os.makedirs(path)


def make_archive_name(name, version, download_url):
    if download_url is None:
        return '{}-{}{}'.format(name, version, '.tar.gz')
    for ext in ARCHIVE_TYPES:
        if download_url.endswith(ext):
            return '{}-{}{}'.format(name, version, ext)
    return None


def which(exe):
    return subprocess.check_output(['which', exe]).rstrip().decode('utf-8')


def import_submodules(package, recursive=True):
    if isinstance(package, str):
        package = importlib.import_module(package)
    results = {}
    for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = package.__name__ + '.' + name
        results[full_name] = importlib.import_module(full_name)
        if recursive and is_pkg:
            results.update(import_submodules(full_name))
    return results


class Dependency(object):
    def __init__(self, name, version, url_pattern, build_group):
        self.name = name
        self.version = version
        self.dir_name = '{}-{}'.format(name, version)
        self.underscored_version = version.replace('.', '_')
        if url_pattern is not None:
            self.download_url = url_pattern.format(version, self.underscored_version)
        else:
            self.download_url = None
        self.build_group = build_group
        self.archive_name = make_archive_name(name, version, self.download_url)
        self.patch_version = 0

    def get_additional_c_cxx_flags(self, builder):
        return []

    def get_additional_c_flags(self, builder):
        return []

    def get_additional_cxx_flags(self, builder):
        return []

    def should_build(self, builder):
        return True


class ExtraDownload(object):
    def __init__(self, name, version, url_pattern, dir_name, post_exec=None):
        self.name = name
        self.version = version
        self.download_url = url_pattern.format(version)
        self.archive_name = make_archive_name(name, version, self.download_url)
        self.dir_name = dir_name
        if post_exec is not None:
            self.post_exec = post_exec


class PushDir:
    def __init__(self, dir_name):
        self.dir_name = dir_name
        self.prev = None

    def __enter__(self):
        self.prev = os.getcwd()
        os.chdir(self.dir_name)

    def __exit__(self, type, value, traceback):
        os.chdir(self.prev)
