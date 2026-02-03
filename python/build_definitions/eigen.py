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
from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class EigenDependency(Dependency):
    def __init__(self) -> None:
        super(EigenDependency, self).__init__(
            name='eigen',
            version='5.0.1',
            url_pattern='https://gitlab.com/libeigen/eigen/-/archive/{0}/eigen-{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    # def get_additional_cmake_args(self, builder: 'BuilderInterface') -> List[str]:
    #     return [
    #             '-DENABLE_MONGOC=OFF',
    #             '-DMONGOC_ENABLE_ICU=OFF'
    #             '-DENABLE_ICU=OFF',
    #             '-DENABLE_ZSTD=OFF',
    #             '-DENABLE_EXTRA_ALIGNMENT=OFF']

    def build(self, builder: BuilderInterface) -> None:
        include_dir =builder.prefix_include
        os.makedirs(include_dir, exist_ok=True)

        for root, _, files in os.walk("Eigen"):
            for file in files:
                src_path = os.path.join(root, file)
                dest_path = os.path.join(include_dir, src_path)
                #print what is being copied
                print(f"Copying {src_path} to {dest_path}")
                # Copy and create the directory if it doesn't exist
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                builder.log_output(builder.log_prefix(self), ['cp', src_path, dest_path])

        # builder.log_output(builder.log_prefix(self), ['cp', 'libbid.a', builder.prefix_lib])
