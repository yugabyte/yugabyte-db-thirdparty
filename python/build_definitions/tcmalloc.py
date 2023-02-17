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
import os


class TCMallocDependency(Dependency):
    def __init__(self) -> None:
        super(TCMallocDependency, self).__init__(
            name='tcmalloc',
            version='e116a66-yb-1',
            url_pattern='https://github.com/yugabyte/tcmalloc/archive/{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        builder.build_with_bazel(dep=self,
                                 targets=["tcmalloc:tcmalloc_shared", "tcmalloc:tcmalloc_static"])

        builder.install_bazel_build_output(
                dep=self,
                src_file="libtcmalloc_shared.so",
                dest_file=f"libgoogletcmalloc.{builder.shared_lib_suffix}",
                src_folder="tcmalloc",
                is_shared=True)
        builder.install_bazel_build_output(
                dep=self, src_file="tcmalloc_static.a", dest_file="libgoogletcmalloc.a",
                src_folder="tcmalloc", is_shared=False)

        # Copy headers, keeping the folder structure. https://stackoverflow.com/a/29457076.
        builder.log_output(log_prefix, ["rsync", "-a", "--include=*.h", "-f",
                                        "hide,! */", "./tcmalloc", builder.prefix_include])
