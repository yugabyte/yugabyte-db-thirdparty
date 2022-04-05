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

from yugabyte_db_thirdparty.util import read_file, write_file

import os


class Icu4cDependency(Dependency):
    VERSION_MAJOR = 70
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
        return []

    def _copy_res_files_from_uninstrumented(self) -> None:
        """
        Updates the following rule in source/extra/uconv/Makefile in ASAN build:

        $(MSGNAME)/%.res: $(srcdir)/$(RESOURCESDIR)/%.txt
            $(INVOKE) $(TOOLBINDIR)/genrb -e UTF-8 -s $(^D) -d $(@D) $(^F)

        The genrb program built with Clang 14 on Linux reports an ODR violation when run with ASAN,
        and the ASAN_OPTIONS=detect_odr_violation=0 flag does not work correctly in Clang 14.
        We work around this by just copying the correspondig .res files from the uninstrumented
        build of icu4c.
        """

        # We are in the "source" directory under the build directory.
        configured_dir = os.getcwd()

        # Get the build directory name, e.g. "icu4c-70_1".
        build_dir_name = os.path.basename(os.path.dirname(configured_dir))

        makefile_path = os.path.join(configured_dir, 'extra', 'uconv', 'Makefile')
        makefile_lines = read_file(makefile_path).split('\n')

        expected_build_rule = '$(INVOKE) $(TOOLBINDIR)/genrb -e UTF-8 -s $(^D) -d $(@D) $(^F)'

        line_found = False
        made_changes = False
        rule_prefix = '$(MSGNAME)/%.res:'
        for i in range(len(makefile_lines) - 1):
            if makefile_lines[i].strip().startswith(rule_prefix):
                line_found = True
                actual_build_rule = makefile_lines[i + 1].strip()
                if (expected_build_rule != actual_build_rule and
                        not actual_build_rule.startswith('cp ')):
                    raise ValueError(
                        "The line %s is followed by %s, not by %s" % (
                            makefile_lines[i].strip(),
                            actual_build_rule,
                            expected_build_rule))
                makefile_lines[i + 1] = ' '.join([
                    '\tcp',
                    '"../../../../../uninstrumented/%s/source/extra/uconv/uconvmsg/$(@F)"' %
                    build_dir_name,
                    '"$@"'
                ])
                made_changes = True
        if not line_found:
            raise IOError('Did not find Makefile rule starting with %s in %s' % (
                rule_prefix, makefile_path))
        if not made_changes:
            log('Did not make any changes to %s, assuming previously applied', makefile_path)
            return
        write_file(makefile_path, '\n'.join(makefile_lines) + '\n')

    def build(self, builder: BuilderInterface) -> None:
        configure_extra_args = [
            '--disable-samples',
            '--disable-tests',
            '--disable-layout',
            '--enable-static',
            '--with-library-bits=64'
        ]

        post_configure_action: Optional[Callable] = None
        llvm_major_version = builder.compiler_choice.get_llvm_major_version()
        if (is_linux() and
                llvm_major_version is not None and
                llvm_major_version >= 14 and
                builder.build_type == BUILD_TYPE_ASAN):
            post_configure_action = self._copy_res_files_from_uninstrumented

        builder.build_with_configure(
            log_prefix=builder.log_prefix(self),
            src_subdir_name='source',
            extra_args=configure_extra_args,
            post_configure_action=post_configure_action
        )

        fix_shared_library_references(builder.prefix, 'libicu')
