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


class TCMallocDependency(Dependency):
    abseil_src_dir_name: str

    def __init__(self) -> None:
        super(TCMallocDependency, self).__init__(
            name='tcmalloc',
            version='31549f83a1f2ca328dee482dd9ed338a2db4e88b',
            url_pattern='https://github.com/google/tcmalloc/archive/{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.patches = ['tcmalloc-yb-cmake-build.patch']

    def set_abseil_source_dir_basename(self, abseil_src_dir_name: str) -> None:
        self.abseil_src_dir_name = abseil_src_dir_name

    def get_additional_cxx_flags(self, builder: 'BuilderInterface') -> List[str]:
        cxx_flags = []
        if (builder.compiler_choice.is_clang() and
                builder.compiler_choice.is_llvm_major_version_at_least(18)):
            cxx_flags.append('-Wno-error=thread-safety-reference-return')
        return cxx_flags

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        abseil_src_dir = os.path.join(builder.fs_layout.tp_src_dir, self.abseil_src_dir_name)
        builder.build_with_cmake(
            dep=self,
            extra_cmake_args=[
                '-DCMAKE_BUILD_TYPE=Release',
                '-DBUILD_SHARED_LIBS=OFF',
                f'-DCMAKE_CXX_STANDARD={constants.CXX_STANDARD}',
                '-DCMAKE_CXX_EXTENSIONS=OFF',
                f'-DABSL_SRC_DIR={abseil_src_dir}',
            ],
            src_subdir_name='yb_cmake',
            extra_build_tool_args=['yb_tcmalloc_closure'],
            should_install=False)

        # Abseil objects are compiled here only as dependencies and are not included, because
        # YugabyteDB links libabsl separately.
        object_files = sorted(glob.glob(os.path.join('tcmalloc', '**', '*.o'), recursive=True))
        static_lib_path = os.path.join(builder.prefix_lib, 'libgoogletcmalloc.a')
        remove_path(static_lib_path)
        builder.log_output(log_prefix, ['ar', 'qc', static_lib_path] + object_files)
        builder.log_output(log_prefix, ['ranlib', static_lib_path])

        shared_lib_name = f'libgoogletcmalloc.{builder.shared_lib_suffix}'
        builder.log_output(
            log_prefix,
            [builder.compiler_choice.get_cxx_compiler()] +
            builder.compiler_flags + builder.cxx_flags +
            ['-shared', '-o', os.path.join(builder.prefix_lib, shared_lib_name),
             '-Wl,-soname,' + shared_lib_name,
             '-Wl,--whole-archive', static_lib_path, '-Wl,--no-whole-archive',
             '-L' + builder.prefix_lib, '-labsl', '-lpthread'] +
            builder.ld_flags)

        # Copy headers, keeping the folder structure. https://stackoverflow.com/a/9626253/1890288.
        src_dir = builder.fs_layout.get_source_path(self)
        builder.log_output(log_prefix, ["rsync", "-a", "--include=*.h", "-f", "hide,! */",
                                        os.path.join(src_dir, 'tcmalloc'),
                                        builder.prefix_include])
