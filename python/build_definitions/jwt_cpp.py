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
from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class JwtCppDependency(Dependency):
    def __init__(self) -> None:
        super(JwtCppDependency, self).__init__(
            'jwt_cpp',
            '0.6.0',
            'https://github.com/Thalhammer/jwt-cpp/archive/refs/tags/v{0}.tar.gz',
            BuildGroup.COMMON)
        self.copy_sources = False

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        builder.log_output(
            log_prefix,
            [
                'rsync', '-av', '--delete',
                os.path.join(builder.fs_layout.get_source_path(self), 'include', 'picojson/'),
                os.path.join(builder.prefix_include, 'picojson')
            ]
        )
        builder.log_output(
            log_prefix,
            [
                'rsync', '-av', '--delete',
                os.path.join(builder.fs_layout.get_source_path(self), 'include', 'jwt-cpp/'),
                os.path.join(builder.prefix_include, 'jwt-cpp')
            ]
        )
