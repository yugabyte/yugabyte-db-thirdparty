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
import subprocess
import platform

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


def use_arm64_bash_in_script(script_path: str) -> None:
    with open(script_path) as script_file:
        lines = [line.rstrip() for line in script_file]

    if not lines:
        return
    if not lines[0].startswith('#!') and lines[0].endswith('bash'):
        return
    lines[0] = '#!/opt/homebrew/bin/bash'
    with open(script_path, 'w') as output_file:
        output_file.write('\n'.join(lines) + '\n')


class OpenSSLDependency(Dependency):
    def __init__(self) -> None:
        super(OpenSSLDependency, self).__init__(
            name='openssl',
            version='1.1.1l',
            url_pattern='https://www.openssl.org/source/openssl-{0}.tar.gz',
            build_group=BUILD_GROUP_COMMON)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        common_configure_options = ['shared']
        install_path = os.path.join(
            builder.fs_layout.tp_installed_common_dir, "lib")
        if platform.system() == 'Darwin' and platform.machine() == 'arm64':
            use_arm64_bash_in_script('config')
        configure_cmd = ['./config'] + common_configure_options
        if not is_macos():
            configure_cmd += ['-Wl,-rpath=' + install_path]

        builder.build_with_configure(
            log_prefix=builder.log_prefix(self),
            configure_cmd=configure_cmd,
            # https://bit.ly/openssl_install_without_manpages
            install=['install_sw']
        )
