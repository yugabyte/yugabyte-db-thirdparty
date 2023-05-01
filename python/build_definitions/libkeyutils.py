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

import glob
from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class LibKeyUtilsDependency(Dependency):
    def __init__(self) -> None:
        super(LibKeyUtilsDependency, self).__init__(
            'libkeyutils',
            '1.6.1-yb-1',
            'https://github.com/yugabyte/libkeyutils/archive/refs/tags/v{0}.tar.gz',
            BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        builder.log_output(log_prefix, ['make'])
        builder.log_output(log_prefix, ['cp'] + glob.glob('*.h') + [builder.prefix_include])
        builder.log_output(
            log_prefix,
            ['cp'] +
            glob.glob('*.a') +
            glob.glob('*.so') +
            glob.glob('*.so.*') +
            [builder.prefix_lib])
