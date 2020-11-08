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


class IncludeWhatYouUseDependency(Dependency):
    URL_PATTERN = 'https://github.com/include-what-you-use/include-what-you-use/archive/{0}.tar.gz'

    def __init__(self) -> None:
        super(IncludeWhatYouUseDependency, self).__init__(
            name='include-what-you-use',
            version='0.11',
            url_pattern=IncludeWhatYouUseDependency.URL_PATTERN,
            build_group=BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(
            self,
            [
                '-DCMAKE_BUILD_TYPE=release',
                '-DBUILD_TOOLS=0',
                '-DCMAKE_PREFIX_PATH={}'.format(builder.prefix),
                '-DCMAKE_INSTALL_PREFIX:PATH={}'.format(builder.prefix)
            ])

    def should_build(self, builder: BuilderInterface) -> bool:
        return builder.compiler_choice.will_need_clang(builder.build_type)
