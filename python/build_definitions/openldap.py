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


class OpenLDAPDependency(Dependency):
    def __init__(self) -> None:
        super(OpenLDAPDependency, self).__init__(
              'openldap',
              '2_4_54',
              'https://github.com/yugabyte/openldap/archive/OPENLDAP_REL_ENG_{}.tar.gz',
              BUILD_GROUP_COMMON)
        self.copy_sources = True

    def get_additional_compiler_flags(self, builder: BuilderInterface) -> List[str]:
        if is_macos():
            return ['-Wno-error=implicit-function-declaration']
        return []

    def build(self, builder: BuilderInterface) -> None:
        # build client only
        disabled_features = (
            'slapd', 'bdb', 'hdb', 'mdb', 'monitor', 'relay', 'syncprov', 'cyrus-sasl'
        )

        builder.build_with_configure(
            builder.log_prefix(self),
            extra_args=['--disable-' + feature for feature in disabled_features])
