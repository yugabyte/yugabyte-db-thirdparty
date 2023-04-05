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


class HdrHistogramPGSSDependency(Dependency):
    def __init__(self) -> None:
        super(HdrHistogramPGSSDependency, self).__init__(
            name='HdrHistogram_c',
            version='v1.1.2',
            url_pattern='https://github.com/acuskev/HdrHistogram_c/archive/refs/tags/{0}.tar.gz',
            build_group=BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        builder.build_with_cmake(self, shared_and_static=True)
        builder.log_output(
            log_prefix,
            [
                'rsync', '-av',
                os.path.join(builder.fs_layout.get_source_path(self), 'include', 'hdr/'),
                os.path.join(builder.prefix_include, 'hdr/')
            ]
        )
