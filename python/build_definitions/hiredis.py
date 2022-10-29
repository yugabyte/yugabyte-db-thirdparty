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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class HiRedisDependency(Dependency):
    def __init__(self) -> None:
        super(HiRedisDependency, self).__init__(
            name='hiredis',
            version='0.13.3',
            url_pattern="https://github.com/redis/hiredis/archive/v{0}.zip",
            build_group=BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        jobs = multiprocessing.cpu_count()
        builder.log_output(
                log_prefix,
                ['make', '-j{}'.format(jobs), 'PREFIX={}'.format(builder.prefix), 'install'])
        fix_shared_library_references(builder.prefix, 'libhiredis')
