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
    abseil_src_dir_name: str

    def __init__(self) -> None:
        super(TCMallocDependency, self).__init__(
            name='tcmalloc',
            version='e116a66-yb-5',
            url_pattern='https://github.com/yugabyte/tcmalloc/archive/{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True
        self.bazel_project_subdir_name = 'com_google_tcmalloc'

    def update_workspace_file(self) -> None:
        """
        The tcmalloc codebase has a WORKSPACE file that has a reference to the Abseil source
        directory. Here, we make sure it refers to the correct location of Abseil source code.
        """
        workspace_file_path = os.path.join(os.getcwd(), 'WORKSPACE')
        with open(workspace_file_path) as workspace_file:
            lines = [line.rstrip() for line in workspace_file.readlines()]
        found = False
        for i in range(len(lines) - 2):
            if (lines[i].strip() == 'local_repository(' and
                    lines[i + 1].strip() == 'name = "com_google_absl",'):
                lines[i + 2] = '    path = "../%s",' % self.abseil_src_dir_name
                found = True
                break
        if not found:
            raise ValueError(
                "Could not update Abseil source path in %s" % workspace_file_path)
        log("Successfully updated Abseil source directory in %s", workspace_file_path)
        with open(workspace_file_path, 'w') as workspace_file:
            workspace_file.write('\n'.join(lines) + '\n')

    def set_abseil_source_dir_basename(self, abseil_src_dir_name: str) -> None:
        self.abseil_src_dir_name = abseil_src_dir_name

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)
        self.update_workspace_file()
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

        # Copy headers, keeping the folder structure. https://stackoverflow.com/a/9626253/1890288.
        builder.log_output(log_prefix, ["rsync", "-a", "--include=*.h", "-f",
                                        "hide,! */", "./tcmalloc", builder.prefix_include])
