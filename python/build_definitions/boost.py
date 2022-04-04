#
# Copyright (c) YugaByte, Inc.
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
import sys
import platform

from typing import Optional

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


PROJECT_CONFIG = """
libraries = {5} ;

using {0} : {1} :
    {2} :
    {3}
    {4} ;
"""


class BoostDependency(Dependency):
    MAJOR_VERSION = 1
    MINOR_VERSION = 78
    PATCH_VERSION = 0
    VERSION_TUPLE = (MAJOR_VERSION, MINOR_VERSION, PATCH_VERSION)
    VERSION_STR = "%s.%s.%s" % VERSION_TUPLE
    VERSION_STR_UNDERSCORES = "%s_%s_%s" % VERSION_TUPLE

    def __init__(self) -> None:
        super(BoostDependency, self).__init__(
            name='boost',
            version=self.VERSION_STR,
            # URL grabbed from https://www.boost.org/users/history/version_1_77_0.html
            url_pattern='https://boostorg.jfrog.io/artifactory/main/release/{}/source/'
                        'boost_{}.tar.bz2'.format(self.VERSION_STR, self.VERSION_STR_UNDERSCORES),
            build_group=BUILD_GROUP_INSTRUMENTED,
            license='Boost Software License 1.0')
        self.dir = '{}_{}'.format(self.name, self.underscored_version)
        self.copy_sources = True
        self.patches = ['boost-1-78-add-arm64-instruction-set.patch']

    def build(self, builder: BuilderInterface) -> None:
        libs = ['system', 'thread', 'atomic', 'program_options', 'regex', 'date_time']

        log_prefix = builder.log_prefix(self)
        prefix = self.get_install_prefix(builder)

        # When building with Clang, we add a directory to PATH which has an ld -> lld symlink,
        # among other symlinks. See create_llvm_tool_dir in clang_util.py for details.
        # For LLVM 14 and later, lld does not support the deprecated --no-add-needed ld flag, and
        # this causes Boost to fail to boostrap its build system, b2. As a workaround, we
        # temporarily add /bin as the first element on PATH in that case.
        llvm_major_version: Optional[int] = builder.compiler_choice.get_llvm_major_version()
        prefer_system_bin = llvm_major_version is not None and llvm_major_version >= 14

        if prefer_system_bin:
            save_path = os.environ['PATH']
            os.environ['PATH'] = '%s:%s' % ('/bin', os.environ['PATH'])

        try:
            log_output(log_prefix, [
                './bootstrap.sh',
                '--prefix={}'.format(prefix),
            ])
        finally:
            if prefer_system_bin:
                os.environ['PATH'] = save_path

        project_config = 'project-config.jam'
        with open(project_config, 'rt') as inp:
            original_lines = inp.readlines()
        with open(project_config, 'wt') as out:
            for line in original_lines:
                lstripped = line.lstrip()
                if (not lstripped.startswith('libraries =') and
                        not lstripped.startswith('using gcc ;') and
                        not lstripped.startswith('project : default-build <toolset>gcc ;')):
                    out.write(line)
            cxx_flags = builder.compiler_flags + builder.cxx_flags
            log("C++ flags to use when building Boost: %s", cxx_flags)
            compiler_type = builder.compiler_choice.compiler_type
            # To make sure Boost's b2 does not select one of its default "toolsets" and ignores all
            # of our compiler flags, we add a "-yb" suffix to the compiler "version" that we give
            # it.--
            compiler_version = '%dyb' % builder.compiler_choice.get_compiler_major_version()
            boost_toolset = '%s-%s' % (compiler_type, compiler_version)
            log("Giving Boost a custom toolset to use: %s", boost_toolset)
            out.write(PROJECT_CONFIG.format(
                    compiler_type,
                    compiler_version,
                    builder.compiler_choice.get_cxx_compiler_or_wrapper(),
                    ' '.join(['<compileflags>' + flag for flag in cxx_flags]),
                    ' '.join(['<linkflags>' + flag for flag in cxx_flags + builder.ld_flags]),
                    ' '.join(['--with-{}'.format(lib) for lib in libs])))
        # -q means stop at first error
        build_cmd = ['./b2', 'install', 'cxxstd=14', 'toolset=%s' % boost_toolset, '-q']
        if is_macos_arm64_build():
            build_cmd.append('instruction-set=arm64')
        log_output(log_prefix, build_cmd)

        if is_macos():
            for lib in libs:
                path = os.path.join(builder.prefix_lib, self.libfile(lib, builder))
                log_output(log_prefix, ['install_name_tool', '-id', path, path])
                for sublib in libs:
                    sublib_file = self.libfile(sublib, builder)
                    sublib_path = os.path.join(builder.prefix_lib, sublib_file)
                    log_output(log_prefix, ['install_name_tool', '-change', sublib_file,
                                            sublib_path, path])

    def libfile(self, lib: str, builder: BuilderInterface) -> str:
        return 'libboost_{}.{}'.format(lib, builder.shared_lib_suffix)
