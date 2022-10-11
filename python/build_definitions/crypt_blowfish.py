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

from shutil import copyfile

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class CryptBlowfishDependency(Dependency):
    def __init__(self) -> None:
        super(CryptBlowfishDependency, self).__init__(
            name='crypt_blowfish',
            # The original project did not have any versions, so we created our own versions.
            version='1.3.2',
            url_pattern='https://github.com/yugabyte/crypt_blowfish/archive/refs/tags/v{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True

    def get_lib_name(self, suffix: str) -> str:
        return 'lib%s.%s' % (self.name, suffix)

    def build(self, builder: BuilderInterface) -> None:
        builder.check_current_dir()
        log_prefix = builder.log_prefix(self)
        log_output(log_prefix, ['make', 'clean'])
        log_output(log_prefix, ['make'])
        crypt_blowfish_include_dir = os.path.join(builder.prefix_include, 'crypt_blowfish')
        mkdir_if_missing(crypt_blowfish_include_dir)
        # Copy over all the headers into a generic include/ directory.
        subprocess.check_call('rsync -av *.h {}'.format(crypt_blowfish_include_dir), shell=True)
        for suffix in ('a', builder.shared_lib_suffix):
            file_name = self.get_lib_name(suffix)
            src_path = os.path.abspath(file_name)
            dest_path = os.path.join(builder.prefix_lib, file_name)
            log("Copying file %s to %s", src_path, dest_path)
            copyfile(src_path, dest_path)
        fix_shared_library_references(builder.prefix, 'lib%s' % self.name)
