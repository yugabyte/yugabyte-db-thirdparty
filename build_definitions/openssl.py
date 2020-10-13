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

from build_definitions import *  # noqa


class OpenSSLDependency(Dependency):
    def __init__(self):
        super(OpenSSLDependency, self).__init__(
                'openssl', '1.0.2u',
                'https://www.openssl.org/source/openssl-{0}.tar.gz',
                BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder):
        common_configure_options = ['shared']
        if is_mac():
            # On macOS x86_64, OpenSSL 1.0.2 fails to detect the proper architecture.
            configure_cmd = [
                '/bin/bash', './Configure', 'darwin64-x86_64-cc'] + common_configure_options
        else:
            install_path = os.path.join(builder.tp_installed_common_dir, "lib")
            configure_cmd = ['./config'] + common_configure_options + ['-Wl,-rpath=' + install_path]

        builder.build_with_configure(
                builder.log_prefix(self),
                configure_cmd=configure_cmd,
                # https://bit.ly/openssl_install_without_manpages
                install=['install_sw'])
