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

class Icu4cDependency(Dependency):
    VERSION_MAJOR = 67
    VERSION_MINOR = 1
    VERSION_WITH_UNDERSCORE = '%d_%d' % (VERSION_MAJOR, VERSION_MINOR)
    VERSION_WITH_DASH = '%d-%d' % (VERSION_MAJOR, VERSION_MINOR)

    def __init__(self):
        super(Icu4cDependency, self).__init__(
            'icu4c',
            Icu4cDependency.VERSION_WITH_UNDERSCORE,
            'http://github.com/unicode-org/icu/releases/download/release-%s/icu4c-%s-src.tgz' % (
                Icu4cDependency.VERSION_WITH_DASH,
                Icu4cDependency.VERSION_WITH_UNDERSCORE),
            BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder):
        builder.build_with_configure(
                builder.log_prefix(self),
                source_subdir='source')
