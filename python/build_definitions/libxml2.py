#
# Copyright (c) Yugabyte, Inc.
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


class LibXml2Dependency(Dependency):
    def __init__(self) -> None:
        super(LibXml2Dependency, self).__init__(
            name='libxml2',
            version='2.13.5',
            url_pattern='https://download.gnome.org/sources/libxml2/2.13/libxml2-2.13.5.tar.xz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(dep=self, extra_configure_args=['--without-python'])
