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
import sys
import multiprocessing

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class GLogDependency(Dependency):
    def __init__(self) -> None:
        super(GLogDependency, self).__init__(
            name='glog',
            version='0.4.0',
            url_pattern='https://github.com/google/glog/archive/v{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True
        self.patch_version = 1
        self.patch_strip = 0
        self.patches = ['glog-tsan-annotations.patch',
                        'glog-application-fingerprint.patch',
                        'glog-symbolize-and-demangle.patch']
        self.post_patch = ['autoreconf', '-fvi']

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(
            dep=self,
            extra_args=[
                '-DCMAKE_BUILD_TYPE=Release',
                '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
                '-DBUILD_SHARED_LIBS=ON',
                '-DBUILD_STATIC_LIBS=ON'
            ])
        return

        log_prefix = builder.log_prefix(self)
        log_output(log_prefix, ['autoreconf', '--force', '--install'])
        args = ['./configure', '--prefix={}'.format(builder.prefix), '--with-pic',
                '--with-gflags={}'.format(builder.prefix)]
        log_output(log_prefix, args)
        log_output(log_prefix, ['make', 'install-exec-am', 'install-data-am',
                                '-j{}'.format(multiprocessing.cpu_count())])
