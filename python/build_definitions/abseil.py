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

        # Copy headers, keeping the folder structure.
        copy_headers_command = "find ./absl -name *.h -exec cp --parents \\{\\} " + \
            builder.prefix_include + " \\;"
        # TODO: Use log_output.
        print("Copying headers: " + copy_headers_command)
        os.system(copy_headers_command)

        # Fix permissions on libraries. Bazel builds write-protected files by default, which
        # prevents overwriting when building thirdparty multiple times.
        builder.log_output(log_prefix, ['chmod', '755', 'bazel-bin/absl/libabsl_shared.so'])
        builder.log_output(log_prefix, ['chmod', '644', 'bazel-bin/absl/absl_static.a'])

        builder.log_output(log_prefix, ['cp',
                                        'bazel-bin/absl/libabsl_shared.so',
                                        builder.prefix_lib + '/libabsl.so'])
        builder.log_output(log_prefix, ['cp', '-f',
                                        'bazel-bin/absl/absl_static.a',
                                        builder.prefix_lib + '/libabsl.a'])
