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


class CurlDependency(Dependency):
    def __init__(self) -> None:
        super(CurlDependency, self).__init__(
            name='curl',
            version='7.70.0',
            url_pattern="https://curl.haxx.se/download/curl-{0}.tar.gz",
            build_group=BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        disabled_features = ['ftp', 'file', 'ldap', 'ldaps', 'rtsp', 'dict', 'telnet', 'tftp',
                             'pop3', 'imap', 'smtp', 'gopher', 'manual', 'librtmp', 'ipv6']
        extra_args = ['--disable-' + feature for feature in disabled_features]

        extra_args.append('--with-ssl=%s' % builder.get_openssl_dir())
        extra_args.append('--with-zlib=%s' % builder.get_openssl_dir())
        extra_args += [
            '--without-brotli',
            '--without-libidn2',
            '--without-librtmp',
            '--without-nghttp2'
        ]

        builder.build_with_configure(dep=self, extra_args=extra_args)

    def use_cppflags_env_var(self) -> bool:
        return True
