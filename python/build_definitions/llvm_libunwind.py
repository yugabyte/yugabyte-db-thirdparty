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
#

import os

from build_definitions.llvm_part import LlvmPartDependencyBase
from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class LlvmLibUnwindDependency(LlvmPartDependencyBase):
    def __init__(self, version: str) -> None:
        super(LlvmLibUnwindDependency, self).__init__(
            name='llvm_libunwind',
            version=version,
            build_group=BuildGroup.COMMON)

    def get_additional_cxx_flags(self, builder: 'BuilderInterface') -> List[str]:
        return ['-D_LIBUNWIND_NO_HEAP']

    def build(self, builder: BuilderInterface) -> None:
        src_subdir_name = 'libunwind'
        source_path = builder.fs_layout.get_source_path(self)
        llvm_path = os.path.join(source_path, 'llvm')
        if not os.path.exists(llvm_path):
            raise IOError(f"Main llvm project directory not found at {llvm_path}")
        builder.build_with_cmake(
            self,
            extra_cmake_args=[
                '-DCMAKE_BUILD_TYPE=Release',
                '-DBUILD_SHARED_LIBS=ON',
                '-DLIBUNWIND_USE_COMPILER_RT=ON',
                # Enable the workaround already present in libunwind's CMakeLists.txt for old
                # versions of CMake and AIX operating system, that ended up being necessary in our
                # case too. Without this, libunwind's .S files are not being compiled, resulting
                # in the missing symbol __unw_getcontext.
                '-DYB_LIBUNWIND_FORCE_ASM_AS_C=ON',
                f'-DLLVM_PATH={llvm_path}',
            ],
            src_subdir_name=src_subdir_name)

        # TODO: do not use this "standalone" build of libunwind -- it is deprecated.
        # https://github.com/yugabyte/yugabyte-db/issues/11962
        # Maybe we won't need to do this manual copying of headers if we use a supported approach.
        src_include_path = os.path.join(source_path, src_subdir_name, 'include')
        dest_include_path = os.path.join(builder.prefix, 'include')
        for root, dirs, files in os.walk(src_include_path):
            for file_name in files:
                if file_name.endswith('.h'):
                    file_path = os.path.abspath(os.path.join(root, file_name))
                    rel_path = os.path.relpath(file_path, src_include_path)
                    dest_path = os.path.join(dest_include_path, rel_path)
                    mkdir_p(os.path.dirname(dest_path))
                    copy_file_and_log(file_path, dest_path)
