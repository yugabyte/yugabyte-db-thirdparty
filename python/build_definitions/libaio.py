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


class LibAIODependency(Dependency):
    def __init__(self) -> None:
        super(LibAIODependency, self).__init__(
            name='libaio',
            version='0.3.113',
            url_pattern='https://github.com/yugabyte/libaio/archive/refs/tags/libaio-{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_make(dep=self, specify_prefix=True, prefix_var='DESTDIR')
