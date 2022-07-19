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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class SqueaselDependency(Dependency):
    def __init__(self) -> None:
        super(SqueaselDependency, self).__init__(
            name='squeasel',
            version='d83cf6d9af0e2c98c16467a6a035ae0d7ca21cb1-yb-1',
            url_pattern='https://github.com/yugabyte/squeasel/archive/squeasel-{0}.tar.gz',
            build_group=BUILD_GROUP_COMMON)
        self.copy_sources = True
        self.patches = ['squeasel_bound_addrs_ipv6.patch']
        self.patch_version = 1
        self.patch_strip = 0

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        compile_command = [
            builder.compiler_choice.get_c_compiler(), '-std=c99', '-O3', '-DNDEBUG', '-DUSE_IPV6',
            '-fPIC', '-c', 'squeasel.c']
        compile_command += builder.preprocessor_flags + builder.compiler_flags + builder.c_flags
        log_output(log_prefix, compile_command)
        log_output(log_prefix, ['ar', 'rs', 'libsqueasel.a', 'squeasel.o'])
        log_output(log_prefix, ['cp', 'libsqueasel.a', builder.prefix_lib])
        log_output(log_prefix, ['cp', 'squeasel.h', builder.prefix_include])
