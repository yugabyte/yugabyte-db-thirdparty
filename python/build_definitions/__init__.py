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

import enum
import os
import sys

import importlib
import pkgutil

from typing import Any, List, Dict, Union, TYPE_CHECKING

from sys_detection import is_macos, is_linux

from yugabyte_db_thirdparty.custom_logging import log
from yugabyte_db_thirdparty.archive_handling import make_archive_name

if TYPE_CHECKING:
    from yugabyte_db_thirdparty.dependency import Dependency


class BuildType(enum.Enum):
    # Dependencies from BuildGroup.COMMON are only built with this build type.
    COMMON = enum.auto()

    # Dependencies from BuildGroup.POTENTIALLY_INSTRUMENTED are built with these build types.
    UNINSTRUMENTED = enum.auto()
    ASAN = enum.auto()  # AddressSanitizer and UndefinedBehaviorSanitizer.
    TSAN = enum.auto()  # ThreadSanitizer

    def dir_name(self) -> str:
        return self.name.lower()

    def is_sanitizer(self) -> bool:
        return self in (BuildType.ASAN, BuildType.TSAN)


class BuildGroup(enum.Enum):
    # Dependencies that are never instrumented with ASAN/UBSAN or TSAN.
    # Also we should not build any C++ code as part of this, only C code.
    COMMON = enum.auto()

    # Dependencies that instrumented with ASAN/UBSAN or TSAN.
    POTENTIALLY_INSTRUMENTED = enum.auto()

    def default_build_type(self) -> BuildType:
        if self == BuildGroup.COMMON:
            return BuildType.COMMON
        if self == BuildGroup.POTENTIALLY_INSTRUMENTED:
            return BuildType.UNINSTRUMENTED
        raise ValueError("Unknown build group: %s" % self)


def is_jenkins_user() -> bool:
    return os.environ['USER'] == "jenkins"


def is_jenkins() -> bool:
    return 'BUILD_ID' in os.environ and 'JOB_NAME' in os.environ and is_jenkins_user()


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


def get_build_def_module(submodule_name: str) -> Any:
    return getattr(sys.modules['build_definitions'], submodule_name)


def get_dependency_by_submodule_name(module_name: str) -> 'Dependency':
    build_def_module = get_build_def_module(module_name)
    candidate_classes: List[Any] = []
    for field_name in dir(build_def_module):
        field_value = getattr(build_def_module, field_name)
        if isinstance(field_value, type):
            try:
                class_name = getattr(field_value, '__name__')
            except AttributeError:
                continue
            if class_name != 'Dependency' and class_name.endswith('Dependency'):
                candidate_classes.append(field_value)

    if not candidate_classes:
        raise ValueError(
            "Could not find a ...Dependency class in module %s that starts with submodule name" %
            module_name)

    if len(candidate_classes) > 1:
        raise ValueError("Found too many classes with names ending with Dependency in module "
                         "%s: %s", module_name, sorted(
                             [cl.__name__ for cl in candidate_classes]))
    return candidate_classes[0]()


def get_deps_from_module_names(module_names: List[str]) -> List['Dependency']:
    return [get_dependency_by_submodule_name(module_name) for module_name in module_names]


COMMON_DEPENDENCY_MODULE_NAMES = [
    # Avoiding a name collision with the standard zlib module, hence "zlib_dependency".
    'zlib_dependency',
    'lz4',
    'openssl',
    'libev',
    'rapidjson',
    'squeasel',
    'curl',
    'hiredis',
    'cqlsh',
    'flex',
    'bison',
    'openldap',
    'redis_cli',
    'wyhash',
    'jwt_cpp',
]


def ensure_build_group(dependencies: List['Dependency'], expected_group: BuildGroup) -> None:
    for dep in dependencies:
        if dep.build_group != expected_group:
            all_dep_names: List[str] = list(set([dep.name for dep in dependencies]))
            all_dep_names_str = ', '.join(all_dep_names)
            raise ValueError(
                f"Expected the given list of dependencies to be in the group {expected_group} "
                f"build group, found: {dep.build_group} for dependency {dep.name}. All "
                f"dependency names subjected to this requirement: {all_dep_names_str}.")


def get_final_dependency_module_names() -> List[str]:
    """
    Returns the list of module names that are added to the end of the list.
    """
    dep_names: List[str] = []

    if is_macos():
        # On macOS, flex, bison, and krb5 depend on gettext, and we don't want to use gettext from
        # Homebrew. libunistring is required by gettext.
        dep_names.extend(['libunistring', 'gettext'])

    dep_names.append('ncurses')

    if is_linux():
        dep_names.extend(['libkeyutils', 'libverto', 'libaio', 'abseil', 'tcmalloc'])

    dep_names.extend([
        'libedit',
        'icu4c',
        'protobuf',
        'crypt_blowfish',
        'boost',
        'gflags',
        'glog',
        'gperftools',
        'googletest',
        'snappy',
        'crcutil',
        'libcds',
        'libuv',
        'cassandra_cpp_driver',
        'krb5',
        'hdrhistogram',
        'otel_proto',
        'otel',
    ])

    if is_linux():
        # TODO: can we build DiskANN on macOS? Particularly, arm64?
        dep_names.append('diskann')

    return dep_names
