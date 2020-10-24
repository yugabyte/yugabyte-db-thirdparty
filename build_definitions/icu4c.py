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
import glob
import subprocess

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa


class Icu4cDependency(Dependency):
    VERSION_MAJOR = 67
    VERSION_MINOR = 1
    VERSION_WITH_UNDERSCORE = '%d_%d' % (VERSION_MAJOR, VERSION_MINOR)
    VERSION_WITH_DASH = '%d-%d' % (VERSION_MAJOR, VERSION_MINOR)
    CUSTOM_URL_PATTERN = \
        'http://github.com/unicode-org/icu/releases/download/release-%s/icu4c-%s-src.tgz'

    def __init__(self) -> None:
        super(Icu4cDependency, self).__init__(
            name='icu4c',
            version=Icu4cDependency.VERSION_WITH_UNDERSCORE,
            url_pattern=Icu4cDependency.CUSTOM_URL_PATTERN % (
                Icu4cDependency.VERSION_WITH_DASH,
                Icu4cDependency.VERSION_WITH_UNDERSCORE),
            build_group=BUILD_GROUP_INSTRUMENTED)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        configure_extra_args = [
            '--disable-samples',
            '--disable-tests',
            '--enable-static',
            '--with-library-bits=64'
        ]

        builder.build_with_configure(
            log_prefix=builder.log_prefix(self),
            src_subdir_name='source',
            extra_args=configure_extra_args
        )

        if is_mac():
            lib_dir = os.path.realpath(os.path.join(builder.prefix, "lib"))
            icu_lib_paths = glob.glob(os.path.join(lib_dir, "libicu*.dylib"))
            bin_dir = os.path.realpath(os.path.join(builder.prefix, "sbin"))
            icu_bin_paths = glob.glob(os.path.join(bin_dir, "*"))

            for icu_lib in icu_lib_paths + icu_bin_paths:
                if os.path.islink(icu_lib):
                    continue
                lib_basename = os.path.basename(icu_lib)

                otool_output = subprocess.check_output(['otool', '-L', icu_lib]).decode('utf-8')

                for line in otool_output.split('\n'):
                    if line.startswith('\tlibicu'):
                        dependency_name = line.strip().split()[0]
                        dependency_real_name = os.path.relpath(
                            os.path.realpath(os.path.join(lib_dir, dependency_name)),
                            lib_dir)

                        if lib_basename in [dependency_name, dependency_real_name]:
                            log("Making %s refer to itself using @rpath", icu_lib)
                            subprocess.check_call([
                                'install_name_tool',
                                '-id',
                                '@rpath/' + dependency_name,
                                icu_lib
                            ])
                        else:
                            log("Making %s refer to %s using @loader_path",
                                icu_lib, dependency_name)
                            subprocess.check_call([
                                'install_name_tool',
                                '-change',
                                dependency_name,
                                '@loader_path/' + dependency_name,
                                icu_lib
                            ])
