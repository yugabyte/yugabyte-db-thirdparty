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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa
from yugabyte_db_thirdparty import constants
import glob
import os


class AbseilDependency(Dependency):
    def __init__(self) -> None:
        super(AbseilDependency, self).__init__(
            name='abseil',
            version='20260526.0',
            url_pattern='https://github.com/abseil/abseil-cpp/archive/refs/tags/{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        builder.build_with_cmake(
            dep=self,
            extra_cmake_args=[
                '-DCMAKE_BUILD_TYPE=Release',
                '-DBUILD_SHARED_LIBS=OFF',
                f'-DCMAKE_CXX_STANDARD={constants.CXX_STANDARD}',
                '-DCMAKE_CXX_EXTENSIONS=OFF',
                '-DABSL_PROPAGATE_CXX_STD=ON',
                '-DABSL_BUILD_TESTING=OFF',
            ],
            should_install=False)

        # YugabyteDB links against one library containing all of Abseil, not the per-component
        # libraries that Abseil's CMake build produces. Object file names are not unique across
        # components, so append ("q") instead of replacing ("r") archive members.
        object_files = sorted(glob.glob(os.path.join('absl', '**', '*.o'), recursive=True))
        static_lib_path = os.path.join(builder.prefix_lib, 'libabsl.a')
        remove_path(static_lib_path)
        builder.log_output(log_prefix, ['ar', 'qc', static_lib_path] + object_files)
        builder.log_output(log_prefix, ['ranlib', static_lib_path])

        shared_lib_name = f'libabsl.{builder.shared_lib_suffix}'
        link_cmd = (
            [builder.compiler_choice.get_cxx_compiler()] +
            builder.compiler_flags + builder.cxx_flags +
            ['-shared', '-o', os.path.join(builder.prefix_lib, shared_lib_name)])
        if is_macos():
            link_cmd += ['-Wl,-install_name,@rpath/' + shared_lib_name,
                         '-Wl,-force_load,' + static_lib_path,
                         '-framework', 'CoreFoundation']
        else:
            link_cmd += ['-Wl,-soname,' + shared_lib_name,
                         '-Wl,--whole-archive', static_lib_path, '-Wl,--no-whole-archive',
                         '-lpthread']
        builder.log_output(log_prefix, link_cmd + builder.ld_flags)

        # Copy headers, keeping the folder structure. https://stackoverflow.com/a/9626253/1890288.
        src_dir = builder.fs_layout.get_source_path(self)
        builder.log_output(log_prefix, ["rsync", "-a", "--include=*.h", "--include=*.inc", "-f",
                                        "hide,! */", os.path.join(src_dir, 'absl'),
                                        builder.prefix_include])
