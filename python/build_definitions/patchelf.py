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

import os

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa

from yugabyte_db_thirdparty import patchelf_util

from typing import Optional


class PatchElfDependency(Dependency):
    def __init__(self) -> None:
        super(PatchElfDependency, self).__init__(
            name='patchelf',
            version='0.18.0',
            url_pattern='https://github.com/yugabyte/patchelf/archive/refs/tags/{0}.zip',
            build_group=BuildGroup.CXX_UNINSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(
            dep=self,
            extra_configure_args=['--with-pic'],
            run_autoreconf=True)
        custom_patchelf_path = patchelf_util.get_custom_patchelf_path()
        if os.path.exists(custom_patchelf_path):
            log("patchelf exists at %s", custom_patchelf_path)
        else:
            raise IOError(f"patchelf still does not exist at {custom_patchelf_path}")
