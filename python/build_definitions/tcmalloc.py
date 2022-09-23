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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa
import glob


class TCMallocDependency(Dependency):
    def __init__(self) -> None:
        super(TCMallocDependency, self).__init__(
            name='tcmalloc',
            version='2',
            url_pattern='https://github.com/SrivastavaAnubhav/tcmalloc/archive/refs/tags/'
                        'v{0}.tar.gz',
            build_group=BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        # Builds just the shared library for now
        log_output(log_prefix, ['bazel', 'build', '//tcmalloc:tcmalloc'])
        log_output(log_prefix, ['cp'] + glob.glob('tcmalloc/*.h') + [builder.prefix_include])
        log_output(
            log_prefix,
            ['cp'] +
            glob.glob('bazel-bin/tcmalloc/*.so') +
            [builder.prefix_lib])
