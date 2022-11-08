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
import os


class AbseilDependency(Dependency):
    def __init__(self) -> None:
        super(AbseilDependency, self).__init__(
            name='abseil',
            version='0064d9d-yb-1',
            url_pattern='https://github.com/yugabyte/abseil-cpp/archive/refs/tags/'
                        '{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        builder.build_with_bazel(dep=self,
                                 targets=["absl:absl_shared", "absl:absl_static"])
        builder.install_bazel_build_output(
                dep=self,
                src_file="libabsl_shared.so",
                dest_file="absl_shared." + builder.shared_lib_suffix,
                src_folder="absl",
                is_shared=True)
        builder.install_bazel_build_output(
                dep=self, src_file="absl_static.a", dest_file="absl_static.a",
                src_folder="absl", is_shared=False)

        # Copy headers, keeping the folder structure. https://stackoverflow.com/a/29457076.
        builder.log_output(log_prefix, ["rsync", "-a", "--include=*.h", "-f", "hide,! */",
                                        "./absl", builder.prefix_include])
