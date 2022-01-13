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


class GPerfToolsDependency(Dependency):
    def __init__(self) -> None:
        super(GPerfToolsDependency, self).__init__(
            name='gperftools',
            version='2.8.1-yb-1',
            url_pattern='https://github.com/yugabyte/gperftools/archive/refs/tags/'
                        'gperftools-{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True
        self.patch_version = 0
        self.post_patch = ['autoreconf', '-fvi']

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        os.environ["YB_REMOTE_COMPILATION"] = "0"
        os.environ['NM'] = '/opt/yb-build/llvm/yb-llvm-v12.0.1-yb-1-1633143152-bdb147e6-almalinux8-x86_64/bin/llvm-nm'
        log_output(log_prefix, ['./configure', '--prefix={}'.format(builder.prefix),
                                '--enable-frame-pointers', '--enable-heap-checker', '--with-pic'])
        log_output(log_prefix, ['make', 'clean'])
        log_output(log_prefix, ['make', 'install', '-j', '1'])

    def should_build(self, builder: BuilderInterface) -> bool:
        return builder.is_release_build()
