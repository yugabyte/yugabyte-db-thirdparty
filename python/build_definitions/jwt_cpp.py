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


class JwtCppDependency(Dependency):
    def __init__(self) -> None:
        super(JwtCppDependency, self).__init__(
            'jwt_cpp',
            '0.6.0',
            'https://github.com/Thalhammer/jwt-cpp/archive/refs/tags/v{0}.tar.gz',
            # Does not require ASAN/TSAN instrumentation since this is a header-only library.
            BuildGroup.COMMON)
        self.copy_sources = False

    def build(self, builder: BuilderInterface) -> None:
        for include_subdir_name in ['picojson', 'jwt-cpp']:
            builder.copy_include_files(
                dep=self,
                rel_src_include_path=os.path.join('include', include_subdir_name),
                dest_include_path=include_subdir_name)
