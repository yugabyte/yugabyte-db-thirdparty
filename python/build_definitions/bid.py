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

import os
import subprocess
from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class BidDependency(Dependency):
    def __init__(self) -> None:
        super(BidDependency, self).__init__(
            name='bid',
            version='20U2',
            url_pattern='https://netlib.org/misc/intel/IntelRDFPMathLib{0}.tar.gz',
            build_group=BuildGroup.CXX_UNINSTRUMENTED)
        self.copy_sources = True

        self.patches = ['bid-crlf.patch']

    def build(self, builder: BuilderInterface) -> None:
        with PushDir("LIBRARY"):
            builder.build_with_make(
                dep=self,
                extra_make_args=['_CFLAGS_OPT=-fPIC',
                                 'CC=gcc',
                                 'CALL_BY_REF=0',
                                 'GLOBAL_RND=0',
                                 'GLOBAL_FLAGS=0',
                                 'UNCHANGED_BINARY_FLAGS=0',
                                 ],
                # Instead of "make install", we do a custom copy command below.
                install_targets=[],
                specify_prefix=True)

            include_dir = os.path.join(builder.prefix_include, "bid")
            builder.log_output(builder.log_prefix(self), ['echo', 'Include path:', include_dir])
            os.makedirs(include_dir, exist_ok=True)

            for root, _, files in os.walk("src"):
                for file in files:
                    if file.endswith(".h"):
                        src_path = os.path.join(root, file)
                        dest_path = os.path.join(include_dir, file)
                        builder.log_output(builder.log_prefix(self), ['cp', src_path, dest_path])

            builder.log_output(builder.log_prefix(self), ['cp', 'libbid.a', builder.prefix_lib])
