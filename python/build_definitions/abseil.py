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

PUBLIC_LIBRARIES_QUERY = (
    'attr(visibility, "//visibility:public", kind("cc_library", //absl/...)) '
    'except attr(testonly, 1, //absl/...)')


class AbseilDependency(Dependency):
    def __init__(self) -> None:
        super(AbseilDependency, self).__init__(
            name='abseil',
            version='20260526.0',
            url_pattern='https://github.com/abseil/abseil-cpp/archive/refs/tags/{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True
        # Abseil's repository name in the Bazel output paths of projects that depend on it.
        self.bazel_project_subdir_name = 'abseil-cpp+'

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)

        # YugabyteDB links against one library containing all of Abseil, not the per-component
        # libraries, so combine the public libraries in a package of our own.
        libraries = builder.query_bazel(PUBLIC_LIBRARIES_QUERY)
        if not libraries:
            raise ValueError("Found no public Abseil libraries")
        shared_lib_name = f'libabsl.{builder.shared_lib_suffix}'
        shared_lib_link_flags = [] if is_macos() else ['-Wl,-soname,' + shared_lib_name]
        os.makedirs('yb_bazel', exist_ok=True)
        with open(os.path.join('yb_bazel', 'BUILD.bazel'), 'w') as build_file:
            build_file.write('\n'.join([
                'load("@rules_cc//cc:cc_shared_library.bzl", "cc_shared_library")',
                'load("@rules_cc//cc:cc_static_library.bzl", "cc_static_library")',
                f'ABSL_LIBRARIES = {libraries!r}',
                'cc_static_library(name = "absl", deps = ABSL_LIBRARIES)',
                'cc_shared_library(',
                '    name = "absl_shared",',
                '    deps = ABSL_LIBRARIES,',
                f'    shared_lib_name = "{shared_lib_name}",',
                f'    user_link_flags = {shared_lib_link_flags!r},',
                ')',
            ]) + '\n')

        builder.build_with_bazel(dep=self, targets=['//yb_bazel:absl', '//yb_bazel:absl_shared'])
        builder.install_bazel_build_output(
                dep=self, src_file='libabsl.a', dest_file='libabsl.a',
                src_folder='yb_bazel', is_shared=False)
        builder.install_bazel_build_output(
                dep=self, src_file=shared_lib_name, dest_file=shared_lib_name,
                src_folder='yb_bazel', is_shared=True)

        # Copy headers, keeping the folder structure. https://stackoverflow.com/a/9626253/1890288.
        builder.log_output(log_prefix, ["rsync", "-a", "--include=*.h", "--include=*.inc", "-f",
                                        "hide,! */", "./absl", builder.prefix_include])
