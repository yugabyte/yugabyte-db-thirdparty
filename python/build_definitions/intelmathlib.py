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
from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa

class IntelMathLibDependency(Dependency):
    def __init__(self) -> None:
        super(IntelMathLibDependency, self).__init__(
            name='intelmathlib',
            version='20U2',
            url_pattern='https://netlib.org/misc/intel/IntelRDFPMathLib{0}.tar.gz',
            build_group=BuildGroup.CXX_UNINSTRUMENTED)
        self.copy_sources = True
        self.patches = ['intelmathlib_macOS_missing_includes.patch',
                        'intelmathlib_macOS_missing_includes_crlf.patch']

    def build(self, builder: BuilderInterface) -> None:
        with PushDir("LIBRARY"):
            builder.build_with_make(
                self,
                extra_make_args =
                    ['_CFLAGS_OPT=-fPIC',
                    'CC=gcc',
                    'CALL_BY_REF=0',
                    'GLOBAL_RND=0',
                    'GLOBAL_FLAGS=0',
                    'UNCHANGED_BINARY_FLAGS=0',
                    ],
                # Instead of "make install", we do a custom copy command below.
                install_targets=[],)

            lib_dir = builder.prefix_lib
            include_dir = builder.prefix_include

            builder.log_output(builder.log_prefix(self), ['echo', 'Library directory:', lib_dir])
            builder.log_output(builder.log_prefix(self), ['echo', 'Library directory:', include_dir])
            # builder.log_output(builder.log_prefix(self), ['cp', '-a', '*.h', include_dir])
            # builder.log_output(builder.log_prefix(self), ['cp', 'libbid.a', lib_dir])
        