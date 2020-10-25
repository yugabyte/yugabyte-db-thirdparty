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
import sys
import subprocess
import shutil

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class LlvmCompilerRTDependency(Dependency):
    def __init__(self) -> None:
        super(LlvmLibUnwindDependency, self).__init__(
            name='llvm_compiler_rt',
            version='10.0.1',
            url_pattern='https://github.com/llvm/llvm-project/archive/llvmorg-{}.tar.gz',
            build_group=BUILD_GROUP_COMMON)

    def build(self, builder: BuilderInterface) -> None:
        src_subdir_name = 'compiler-rt'
        builder.build_with_cmake(
            self,
            extra_args=[
                '-DCMAKE_BUILD_TYPE=Release',
                '-DBUILD_SHARED_LIBS=ON',
                '-DLLVM_PATH=%s' % builder.source_path(self),
                '-DCMAKE_INSTALL_PREFIX={}'.format(builder.prefix),
            ],
            src_subdir_name=src_subdir_name)
