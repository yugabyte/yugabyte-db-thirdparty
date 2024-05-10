# Copyright (c) YugabyteDB, Inc.
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

from sys_detection import is_macos, is_linux

from typing import List

from yugabyte_db_thirdparty.arch import is_building_for_x86_64
from yugabyte_db_thirdparty.compiler_choice import CompilerChoice


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


def get_final_dependency_module_names(compiler_choice: CompilerChoice) -> List[str]:
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

    if is_linux() and is_building_for_x86_64() and compiler_choice.is_clang():
        # TODO: support all other configurations too.
        dep_names.append('diskann')

    return dep_names
