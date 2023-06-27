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
import subprocess

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class GoogleTestDependency(Dependency):
    def __init__(self) -> None:
        super(GoogleTestDependency, self).__init__(
            name='googletest',
            version='1.12.1',
            url_pattern='https://github.com/google/googletest/archive/release-{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.dir = "googletest-release-{}".format(self.version)
        self.copy_sources = False

    def build(self, builder: BuilderInterface) -> None:
        self.do_build(builder, 'static')
        self.do_build(builder, 'shared')
        lib_dir = builder.prefix_lib
        include_dir = builder.prefix_include
        for lib in ['gmock', 'gtest']:
            log("Installing " + lib + " (static)")
            subprocess.check_call(['cp', '-a', 'static/lib/lib' + lib + '.a', lib_dir])
            log("Installing " + lib + " (shared)")
            for suffix in ['', '.' + self.version]:
                if is_macos():
                    suffix += '.' + builder.shared_lib_suffix
                else:
                    suffix = '.' + builder.shared_lib_suffix + suffix
                subprocess.check_call([
                    'cp', '-a', 'shared/lib/lib{}{}'.format(lib, suffix), lib_dir])

        src_dir = builder.fs_layout.get_source_path(self)
        subprocess.check_call(
                ['rsync', '-av', os.path.join(src_dir, 'googlemock', 'include/'), include_dir])
        subprocess.check_call(
                ['rsync', '-av', os.path.join(src_dir, 'googletest', 'include/'), include_dir])

    def do_build(self, builder: BuilderInterface, mode: str) -> None:
        assert mode in ['shared', 'static']
        build_dir = os.path.join(os.getcwd(), mode)
        mkdir_p(build_dir)
        cmake_opts = ['-DCMAKE_BUILD_TYPE=Debug',
                      '-DBUILD_SHARED_LIBS={}'.format('ON' if mode == 'shared' else 'OFF')]
        if is_macos():
            cmake_opts += ['-DCMAKE_MACOSX_RPATH=ON']
        with PushDir(build_dir):
            builder.build_with_cmake(
                    self,
                    cmake_opts,
                    should_install=False)
