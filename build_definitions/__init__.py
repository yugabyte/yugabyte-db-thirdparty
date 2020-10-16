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

from typing import Any, List, Optional, Dict, Union, NoReturn


YB_THIRDPARTY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if not os.path.isdir(os.path.join(YB_THIRDPARTY_DIR, 'python', 'yugabyte_db_thirdparty')):
    raise IOError("Could not identify correct third-party directory, got %s" % YB_THIRDPARTY_DIR)


YELLOW_COLOR = "\033[0;33m"
RED_COLOR = "\033[0;31m"
CYAN_COLOR = "\033[0;36m"
NO_COLOR = "\033[0m"
SEPARATOR = "-" * 80

# -------------------------------------------------------------------------------------------------
# Build groups
# -------------------------------------------------------------------------------------------------

# These are broad groups of dependencies.

# Dependencies that are never instrumented with ASAN/UBSAN or TSAN.
# Also we should not build any C++ code as part of this. Only C code
# TODO: should we actually instrument some of these?
BUILD_GROUP_COMMON = 'build_group_common'

# TODO: this should be called BUILD_GROUP_POTENTIALLY_INSTRUMENTED, because we only instrument these
# dependencies for special builds like ASAN/TSAN.
BUILD_GROUP_INSTRUMENTED = 'build_group_potentially_instrumented'
VALID_BUILD_GROUPS = [BUILD_GROUP_COMMON, BUILD_GROUP_INSTRUMENTED]

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


def _args_to_message(*args: Any) -> str:
    n_args = len(args)
    if n_args == 0:
        message = ""
    elif n_args == 1:
        message = args[0]
    else:
        message = args[0] % args[1:]
    return message


def fatal(*args: Any) -> NoReturn:
    log(*args)
    traceback.print_stack()
    sys.exit(1)


def log(*args: Any) -> None:
    sys.stderr.write(_args_to_message(*args) + "\n")


def colored_log(color: str, *args: Any) -> None:
    sys.stderr.write(color + _args_to_message(*args) + NO_COLOR + "\n")


def print_line_with_colored_prefix(prefix: str, line: str) -> None:
    log("%s[%s] %s%s", CYAN_COLOR, prefix, NO_COLOR, line.rstrip())


def log_output(prefix: str, args: List[Any], log_cmd: bool = True) -> None:
    try:
        print_line_with_colored_prefix(
            prefix, "Running command: {} (current directory: {})".format(
                args, os.getcwd()))
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert process.stdout is not None
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


def unset_env_var_if_set(name: str) -> None:
    if name in os.environ:
        log('Unsetting %s for third-party build (was set to "%s").', name, os.environ[name])
        del os.environ[name]


def log_separator() -> None:
    log("")
    log(SEPARATOR)
    log("")


def heading(title: str) -> None:
    log("")
    log(SEPARATOR)
    log(title)
    log(SEPARATOR)
    log("")


def is_mac() -> bool:
    return platform.system().lower() == 'darwin'


def is_linux() -> bool:
    return platform.system().lower() == 'linux'


def is_jenkins_user() -> bool:
    return os.environ['USER'] == "jenkins"


def is_jenkins() -> bool:
    return 'BUILD_ID' in os.environ and 'JOB_NAME' in os.environ and is_jenkins_user()


def does_file_start_with_string(file_path: str, s: str) -> bool:
    if not os.path.exists(file_path):
        return False
    with open(file_path) as f:
        return f.read().strip().startswith(s)


IS_UBUNTU = does_file_start_with_string('/etc/issue', 'Ubuntu')
IS_CENTOS = does_file_start_with_string('/etc/centos-release', 'CentOS')


def is_ubuntu() -> bool:
    return IS_UBUNTU


def is_centos() -> bool:
    return IS_CENTOS


def remove_path(path: str) -> None:
    if not os.path.exists(path):
        return
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def mkdir_if_missing(path: str) -> None:
    if os.path.exists(path):
        if not os.path.isdir(path):
            fatal("Trying to create dir {}, but file with the same path already exists"
                  .format(path))
        return
    os.makedirs(path)


def make_archive_name(name: str, version: str, download_url: Optional[str]) -> Optional[str]:
    if download_url is None:
        return '{}-{}{}'.format(name, version, '.tar.gz')
    for ext in ARCHIVE_TYPES:
        if download_url.endswith(ext):
            return '{}-{}{}'.format(name, version, ext)
    return None


def which(exe: str) -> str:
    return subprocess.check_output(['which', exe]).rstrip().decode('utf-8')


def import_submodules(package: Any, recursive: bool = True) -> Dict[str, Any]:
    if isinstance(package, str):
        package = importlib.import_module(package)
    results = {}
    for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = package.__name__ + '.' + name
        results[full_name] = importlib.import_module(full_name)
        if recursive and is_pkg:
            results.update(import_submodules(full_name))
    return results


class BuilderInterface:
    prefix: str
    compiler_flags: List[str]
    c_flags: List[str]
    cxx_flags: List[str]
    compiler_type: str
    prefix_lib: str
    prefix_bin: str
    ld_flags: List[str]
    dylib_suffix: str
    tp_installed_common_dir: str
    prefix_include: str
    tp_dir: str
    build_type: str

    def build_with_configure(
            self,
            log_prefix: str,
            extra_args: List[str] = [],
            configure_cmd: List[str] = ['./configure'],
            install: List[str] = ['install'],
            run_autogen: bool = False,
            autoconf: bool = False,
            src_subdir_name: Optional[str] = None) -> None:
        raise NotImplementedError()

    def build_with_cmake(
            self,
            dep: 'Dependency',
            extra_args: List[str] = [],
            use_ninja_if_available: bool = False,
            src_subdir_name: Optional[str] = None,
            should_install: bool = True) -> None:
        raise NotImplementedError()

    def log_prefix(self, dep: 'Dependency') -> str:
        raise NotImplementedError()

    def get_c_compiler(self) -> str:
        raise NotImplementedError()

    def get_cxx_compiler(self) -> str:
        raise NotImplementedError()

    def prepend_rpath(self, path: str) -> None:
        # TODO: should dependencies really be calling this?
        raise NotImplementedError()

    def source_path(self, dep: 'Dependency') -> str:
        raise NotImplementedError()

    def cmake_build_type_for_test_only_dependencies(self) -> str:
        raise NotImplementedError()

    def get_openssl_related_cmake_args(self) -> List[str]:
        raise NotImplementedError()

    def add_checked_flag(self, flags: List[str], flag: str) -> None:
        raise NotImplementedError()

    def building_with_clang(self) -> bool:
        raise NotImplementedError()

    def get_openssl_dir(self) -> str:
        raise NotImplementedError()

    def is_release_build(self) -> bool:
        raise NotImplementedError()

    def will_need_clang(self) -> bool:
        raise NotImplementedError()

    def get_prefix(self, qualifier: Optional[str] = None) -> str:
        raise NotImplementedError()


class ExtraDownload:
    def __init__(
            self,
            name: str,
            version: str,
            url_pattern: str,
            dir_name: str,
            post_exec: Union[None, List[str], List[List[str]]] = None) -> None:
        self.name = name
        self.version = version
        self.download_url = url_pattern.format(version)
        self.archive_name = make_archive_name(name, version, self.download_url)
        self.dir_name = dir_name
        self.post_exec = post_exec


class Dependency:
    download_url: Optional[str]
    extra_downloads: List[ExtraDownload]
    patches: List[str]
    patch_strip: Optional[int]
    post_patch: List[str]
    copy_sources: bool

    def __init__(
            self,
            name: str,
            version: str,
            url_pattern: Optional[str],
            build_group: str) -> None:
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
        self.extra_downloads = []
        self.patches = []
        self.patch_strip = None
        self.post_patch = []
        self.copy_sources = False

        if build_group not in VALID_BUILD_GROUPS:
            raise ValueError("Invalid build group: %s, should be one of: %s" % (
                build_group, VALID_BUILD_GROUPS))

    def get_additional_c_cxx_flags(self, builder: BuilderInterface) -> List[str]:
        return []

    def get_additional_c_flags(self, builder: BuilderInterface) -> List[str]:
        return []

    def get_additional_cxx_flags(self, builder: BuilderInterface) -> List[str]:
        return []

    def should_build(self, builder: BuilderInterface) -> bool:
        return True

    def build(self, builder: BuilderInterface) -> None:
        raise NotImplementedError()


class PushDir:
    dir_name: str
    prev: Optional[str]

    def __init__(self, dir_name: str) -> None:
        self.dir_name = dir_name
        self.prev = None

    def __enter__(self) -> None:
        self.prev = os.getcwd()
        os.chdir(self.dir_name)

    def __exit__(self, type: Any, value: Any, traceback: Any) -> None:
        # TODO: use more precise argument types above.
        assert self.prev is not None
        os.chdir(self.prev)


def get_build_def_module(submodule_name: str) -> Any:
    return getattr(sys.modules['build_definitions'], submodule_name)
