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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class LlvmLibUnwindDependency(Dependency):
    def __init__(self, version: str) -> None:
        super(LlvmLibUnwindDependency, self).__init__(
            name='llvm_libunwind',
            version=version,
            build_group=BuildGroup.COMMON,
            url_pattern=None,
            mkdir_only=True)

    def build(self, builder: BuilderInterface) -> None:
        # This is only None for non-llvm-installer builds, and this dependency is
        # llvm-installer specific.
        assert builder.toolchain is not None

        # We copy libunwind headers and libraries from the toolchain directly so that we run
        # with the same libunwind that we link with (our build RPATH points only to thirdparty and
        # not to the toolchain, so we need a copy in thirdparty).
        toolchain_root = builder.toolchain.toolchain_root
        src_include_path = os.path.join(toolchain_root, 'include')
        dest_include_path = os.path.join(builder.prefix, 'include')
        for root, dirs, files in os.walk(src_include_path):
            for file_name in files:
                if file_name.endswith('.h') and 'unwind' in file_name:
                    file_path = os.path.abspath(os.path.join(root, file_name))
                    rel_path = os.path.basename(file_name)
                    dest_path = os.path.join(dest_include_path, rel_path)
                    mkdir_p(os.path.dirname(dest_path))
                    copy_file_and_log(file_path, dest_path)

        src_lib_path = os.path.join(toolchain_root, 'lib')
        dest_lib_path = os.path.join(builder.prefix, 'lib')
        for root, dirs, files in os.walk(src_lib_path):
            for file_name in files:
                if 'unwind' in file_name:
                    file_path = os.path.abspath(os.path.join(root, file_name))
                    rel_path = os.path.basename(file_name)
                    dest_path = os.path.join(dest_lib_path, rel_path)
                    mkdir_p(os.path.dirname(dest_path))
                    copy_file_and_log(file_path, dest_path)
