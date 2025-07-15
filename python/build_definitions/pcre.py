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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa

class PcreDependency(Dependency):
    def __init__(self) -> None:
        super(PcreDependency, self).__init__(
            name='pcre',
            version='10.40',
            url_pattern='https://github.com/PCRE2Project/pcre2/releases/download/pcre2-{0}/'
                        'pcre2-{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(
            dep=self,
            extra_configure_args=[
                '--with-pic', '--enable-static', '--enable-jit'
            ]
        )
