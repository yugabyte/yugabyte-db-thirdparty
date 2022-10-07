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

import multiprocessing
import os

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class XXHashDependency(Dependency):
    def __init__(self) -> None:
        super(XXHashDependency, self).__init__(
            name='xxhash',
            version='0.8.1',
            url_pattern='https://github.com/Cyan4973/xxHash/archive/refs/tags/v{0}.tar.gz',
            build_group=BUILD_GROUP_COMMON)
        self.dir = 'xxhash-{}'.format(self.version)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        os.environ["PREFIX"] = builder.prefix
        log_output(log_prefix, ['make', '-j{}'.format(multiprocessing.cpu_count())])
        log_output(log_prefix, ['make', 'install'])
        del os.environ["PREFIX"]
