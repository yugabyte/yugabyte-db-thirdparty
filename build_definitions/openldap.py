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
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from build_definitions import *

class OpenLDAPDependency(Dependency):
    def __init__(self):
        super(OpenLDAPDependency, self).__init__(
              'openldap',
              '2_4_54',
              'https://github.com/yugabyte/openldap/archive/OPENLDAP_REL_ENG_{}.tar.gz',
              BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder):
        # build client only
        disabled_features = ('slapd', 'bdb', 'hdb', 'mdb', 'monitor', 'relay', 'syncprov')

        builder.build_with_configure(
            builder.log_prefix(self), ['--disable-' + feature for feature in disabled_features])
