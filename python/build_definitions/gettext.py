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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class GetTextDependency(Dependency):
    def __init__(self) -> None:
        super(GetTextDependency, self).__init__(
            'gettext',
            '0.21',
            'https://ftp.gnu.org/pub/gnu/gettext/gettext-{0}.tar.gz',
            BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def get_compiler_wrapper_ld_flags_to_remove(self, builder: BuilderInterface) -> Set[str]:
        if is_macos():
            return {'-lrt'}
        return set()

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        flags = []
        if is_macos():
            # See the links for the errors.
            flags.extend([
                # https://gist.githubusercontent.com/hari90/884042ede3a0d408b215bff43ec1c17c/raw
                '-Wno-deprecated-declarations',
                # https://gist.githubusercontent.com/hari90/c8e928aac8f9e9023bb5ae7258a18735/raw
                '-Wno-error=incompatible-function-pointer-types'
            ])
        return flags

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(
            dep=self,
            extra_configure_args=[
                '--with-included-gettext',
                '--disable-java',
                '--disable-csharp',
                '--without-git',
                '--without-cvs',
                '--without-xz',
            ])
