#
# Copyright (c) YugabyteDB, Inc.
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
import shutil

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa
from yugabyte_db_thirdparty.env_helpers import EnvVarContext


# DuckDB is consumed by the pg_duckdb PostgreSQL extension in the yugabyte-db repo. Rather than
# embedding DuckDB's ~14k source files in yugabyte-db (as a submodule or subtree) and recompiling it
# on every fresh build, we build it once here and publish libduckdb_bundle.a plus DuckDB's internal
# header tree as a thirdparty artifact. pg_duckdb relies on DuckDB's private headers (not just the
# public amalgamation), so the full src/include tree is shipped.
#
# The pin below must match upstream pg_duckdb's DuckDB submodule pointer and DUCKDB_VERSION in
# pg_duckdb's Makefile. For v1.4.3 the submodule SHA d1dc88f950d456d72493df452dabdcd13aa413dd is the
# v1.4.3 release tag, so the release tarball matches the pin exactly. On a pg_duckdb rebase, read
# the new submodule SHA upstream and update DUCKDB_VERSION (and the pin if it diverges from a tag).
DUCKDB_VERSION = '1.4.3'

# DuckDB extensions to compile into the bundle. This MUST stay in sync with
# src/postgres/third-party-extensions/pg_duckdb/third_party/pg_duckdb_extensions.cmake in the
# yugabyte-db repo. httpfs is fetched from its own git repo during the DuckDB CMake configure step
# (it provides S3/HTTP read support that pg_duckdb depends on).
PG_DUCKDB_EXTENSIONS_CMAKE = """\
duckdb_extension_load(json)
duckdb_extension_load(icu)
duckdb_extension_load(httpfs
    GIT_URL https://github.com/duckdb/duckdb-httpfs
    GIT_TAG 9c7d34977b10346d0b4cbbde5df807d1dab0b2bf
)
"""


class DuckDBDependency(Dependency):
    def __init__(self) -> None:
        super(DuckDBDependency, self).__init__(
            name='duckdb',
            version=DUCKDB_VERSION,
            url_pattern='https://github.com/duckdb/duckdb/archive/refs/tags/v{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED,
            license='MIT')
        # DuckDB's own Makefile/CMake builds in-source (into build/release/), so build on a copy of
        # the extracted sources rather than polluting the downloaded tree.
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        if not builder.prepare_for_build_tool_invocation(self):
            return

        log_prefix = builder.log_prefix(self)
        src_path = builder.fs_layout.get_source_path(self)

        # Materialize the extension config DuckDB's Makefile expects via EXTENSION_CONFIGS.
        ext_config_path = os.path.join(src_path, 'pg_duckdb_extensions.cmake')
        with open(ext_config_path, 'w') as ext_config_file:
            ext_config_file.write(PG_DUCKDB_EXTENSIONS_CMAKE)

        # httpfs needs OpenSSL. We do not use vcpkg here; instead we point DuckDB's find_package at
        # the OpenSSL we already built in thirdparty. OpenSSL is a COMMON dependency, so it lives in
        # installed/common, not in the per-build-type prefix. Search both (common first) so
        # find_package(OpenSSL) and any other find_package resolve correctly.
        common_dir = builder.fs_layout.tp_installed_common_dir
        cmake_vars = ' '.join([
            '-DCXX_EXTRA=-fvisibility=default',
            '-DBUILD_SHELL=0',
            '-DBUILD_PYTHON=0',
            '-DBUILD_UNITTESTS=0',
            '-DOPENSSL_ROOT_DIR=' + common_dir,
            # CMAKE_VARS is expanded unquoted into a shell `cmake ...` recipe in DuckDB's Makefile,
            # so the ';' list separator must be single-quoted or the shell would treat it as a
            # command terminator (DuckDB's Makefile uses the same single-quoting idiom elsewhere).
            "-DCMAKE_PREFIX_PATH='" + common_dir + ';' + builder.prefix + "'",
        ])

        build_env = {
            # Stamps the DuckDB version into the binary without requiring a git checkout.
            'OVERRIDE_GIT_DESCRIBE': 'v' + DUCKDB_VERSION,
            'GEN': 'ninja',
            'CMAKE_VARS': cmake_vars,
            'DISABLE_SANITIZER': '1',
            'DISABLE_ASSERTIONS': '0',
            'EXTENSION_CONFIGS': ext_config_path,
        }

        with PushDir(src_path):
            # The bundle assembly step (`make bundle-library`) globs build/release/vcpkg_installed
            # for static libs. We don't use vcpkg, so create the directory empty to match the
            # ReleaseStatic build path pg_duckdb uses upstream.
            mkdir_p(os.path.join(src_path, 'build', 'release', 'vcpkg_installed'))
            with EnvVarContext(**build_env):
                # `bundle-library` builds the `release` target and packs every static lib
                # (libduckdb_static.a, third_party/*, extensions, vcpkg) into libduckdb_bundle.a.
                builder.log_output(log_prefix, ['make', 'bundle-library'])

        self.install_artifacts(builder, src_path)

    def install_artifacts(self, builder: BuilderInterface, src_path: str) -> None:
        # The single static bundle pg_duckdb links against.
        bundle_lib = os.path.join(src_path, 'build', 'release', 'libduckdb_bundle.a')
        if not os.path.exists(bundle_lib):
            raise IOError("Expected DuckDB bundle library not found: %s" % bundle_lib)
        mkdir_p(builder.prefix_lib)
        shutil.copy(bundle_lib, os.path.join(builder.prefix_lib, 'libduckdb_bundle.a'))

        # pg_duckdb compiles with:
        #   -isystem <duckdb>/src/include      (resolves duckdb.hpp and duckdb/<...>)
        #   -isystem <duckdb>/third_party/re2  (resolves re2/<...>)
        # Mirror those into dedicated include subdirs so pg_duckdb's Makefile can -isystem them
        # without clobbering other thirdparty headers.
        builder.copy_include_files(
            dep=self,
            rel_src_include_path='src/include',
            dest_include_path='duckdb_internal')
        builder.copy_include_files(
            dep=self,
            rel_src_include_path='third_party/re2',
            dest_include_path='duckdb_re2')
