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
import subprocess
import sys

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class SnappyDependency(Dependency):
    def __init__(self) -> None:
        super(SnappyDependency, self).__init__(
            name='snappy',
            version='1.1.3',
            url_pattern='https://github.com/google/snappy/archive/{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True
        self.patch_version = 1
        self.patch_strip = 1
        self.patches = ['snappy-define-guard-macro.patch']
        self.post_patch = ['autoreconf', '-fvi']

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        builder.build_with_configure(
            log_prefix=log_prefix,
            extra_args=['--with-pic']
        )
        # Copy over all the headers into a generic include/ directory.
        mkdir_if_missing('include')
        subprocess.check_call('ls | egrep "snappy.*.h" | xargs -I{} rsync -av "{}" "include/"',
                              shell=True)

        # Copy over all the libraries into a generic lib/ directory.
        mkdir_if_missing('lib')
        subprocess.check_call('ls ".libs/" | xargs -I{} rsync -av ".libs/{}" "lib/"', shell=True)
