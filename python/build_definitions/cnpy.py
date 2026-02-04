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


class CnpyDependency(Dependency):
    def __init__(self) -> None:
        super(CnpyDependency, self).__init__(
            name='cnpy',
            version='57184ee0db37cac383fc29175950747a46a8b512',
            url_pattern='https://github.com/sammymax/cnpy/archive/'
                        '{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(self, shared_and_static=True)

        include_dir = os.path.join(builder.prefix_include, "cnpy")
        os.makedirs(include_dir, exist_ok=True)
        dest_path = os.path.join(include_dir, 'cnpy.h')
        file_path = os.path.join('cnpy', 'cnpy.h')
        builder.log_output(builder.log_prefix(self), ['cp', file_path, dest_path])
