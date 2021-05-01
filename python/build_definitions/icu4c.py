# Copyright (c) Yugabyte, Inc.
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
from yugabyte_db_thirdparty.rpath_fixes import fix_shared_library_references


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

    def get_additional_ld_flags(self, builder: BuilderInterface) -> List[str]:
        if builder.compiler_choice.is_linux_clang1x() and builder.build_type == BUILD_TYPE_ASAN:
            # Needed to find dlsym.
            return ['-ldl']

        compiler_choice = builder.compiler_choice
        if (compiler_choice.single_compiler_type == 'clang' and
                compiler_choice.get_llvm_major_version() == 7):
            # This is needed with a standalone Clang 7 build (without Linuxbrew) to avoid the 
            # following error:
            # ld: makeconv.o: undefined reference to symbol '_Unwind_Resume@@GCC_3.0'
            # /lib64/libgcc_s.so.1: error adding symbols: DSO missing from command line
            return ['-lgcc_s']

        return []

    def build(self, builder: BuilderInterface) -> None:
        configure_extra_args = [
            '--disable-samples',
            '--disable-tests',
            '--disable-layout',
            '--enable-static',
            '--with-library-bits=64'
        ]

        builder.build_with_configure(
            log_prefix=builder.log_prefix(self),
            src_subdir_name='source',
            extra_args=configure_extra_args
        )

        fix_shared_library_references(self.get_install_prefix(builder), 'libicu')
