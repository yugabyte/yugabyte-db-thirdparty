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


class LibVertoDependency(Dependency):
    """
    libverto is one of the dependencies of libkrad, which is part of Kerberos.
    """
    def __init__(self) -> None:
        super(LibVertoDependency, self).__init__(
            'libverto',
            '0.3.2',
            'https://github.com/latchset/libverto/releases/download/{0}/libverto-{0}.tar.gz',
            BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        builder.build_with_configure(
            dep=self,
            extra_configure_args=['--without-glib', '--without-libevent', '--with-libev'])
