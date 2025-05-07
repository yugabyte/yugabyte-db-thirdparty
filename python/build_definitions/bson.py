#
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
#

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class BsonDependency(Dependency):
    def __init__(self) -> None:
        super(BsonDependency, self).__init__(
            name='bson',
            version='1.28.0',
            url_pattern='https://github.com/mongodb/mongo-c-driver/archive/refs/tags/'
                        '{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def get_additional_cmake_args(self, builder: 'BuilderInterface') -> List[str]:
        return [
                '-DENABLE_MONGOC=OFF',
                '-DMONGOC_ENABLE_ICU=OFF'
                '-DENABLE_ICU=OFF',
                '-DENABLE_ZSTD=OFF',
                '-DENABLE_EXTRA_ALIGNMENT=OFF']

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_cmake(self, shared_and_static=True)
