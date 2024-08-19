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

from yugabyte_db_thirdparty.build_definition_helpers import *

import os
import shutil


class ClockBoundDependency(Dependency):
    """
    aws/clock-bound is a convenience library to retrieve a strict ambiguity
    time window within which the current reference clock's timestamp
    is guaranteed to be present.

    YB links target/release/libclockbound.so shared lib that provides the above
    implementation.

    YB includes clock-bound-ffi/include/clockbound.h header file that provides
    the corresponding C interface.
    """
    def __init__(self) -> None:
        super(ClockBoundDependency, self).__init__(
            name='clockbound',
            version='main',
            url_pattern='https://github.com/aws/clock-bound/archive/{0}.zip',
            build_group=BuildGroup.COMMON)

    def build(self, builder: BuilderInterface) -> None:
        with PushDir(builder.fs_layout.get_source_path(self)):
            self.build_clockbound_ffi(builder)
        self.lib_install_clockbound_ffi(builder)
        self.hdr_install_clockbound_ffi(builder)

    def build_clockbound_ffi(self, builder: BuilderInterface) -> None:
        """ cargo build --release """
        if not builder.prepare_for_build_tool_invocation(self):
            return
        log_prefix = builder.log_prefix(self)
        log("Building dependency %s using Cargo", self.name)
        builder.log_output(log_prefix, ['cargo', 'build', '--release'])

    def lib_install_clockbound_ffi(self, builder: BuilderInterface) -> None:
        """ cp target/release/libclockbound.a $INSTALL_PREFIX/lib """
        src_dir = builder.fs_layout.get_source_path(self)
        src_path = os.path.join(src_dir, 'target', 'release', 'libclockbound.a')
        dst_path = os.path.join(builder.fs_layout.tp_installed_common_dir, "lib")

        # Copy the shared library to the destination directory.
        log("Copying %s to %s", src_path, dst_path)
        shutil.copy(src_path, dst_path)

    def hdr_install_clockbound_ffi(self, builder: BuilderInterface) -> None:
        """ cp clockbound-ffi/include/clockbound.h $INSTALL_PREFIX/include """
        src_dir = builder.fs_layout.get_source_path(self)
        src_path = os.path.join(src_dir, 'clock-bound-ffi', 'include', 'clockbound.h')
        dst_path = os.path.join(builder.fs_layout.tp_installed_common_dir, "include")

        # Copy the header file to the destination directory.
        log("Copying %s to %s", src_path, dst_path)
        shutil.copy(src_path, dst_path)
