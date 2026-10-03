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


class LibUringDependency(Dependency):
    def __init__(self) -> None:
        super(LibUringDependency, self).__init__(
            name='liburing',
            version='2.5',
            url_pattern='https://github.com/axboe/liburing/archive/refs/tags/liburing-{0}.tar.gz',
            build_group=BuildGroup.COMMON)
        self.copy_sources = True

    def build(self, builder: BuilderInterface) -> None:
        # Build and install only the library subdirectory (src/). We intentionally do not build
        # liburing's test/ and examples/ programs: they can require newer kernel headers than the
        # build host provides, and we only need the library and its headers.
        #
        # liburing's ./configure writes the install prefix into config-host.mak, which src/Makefile
        # includes, so `make -C src install` honors the --prefix passed by build_with_configure.
        builder.build_with_configure(
            dep=self,
            extra_make_args=['-C', 'src'],
            install_targets=['-C', 'src', 'install'])

    def get_additional_ld_flags(self, builder: 'BuilderInterface') -> List[str]:
        flags: List[str] = []
        if builder.compiler_choice.is_clang():
            # liburing 2.5's liburing-ffi.map version script exports io_uring_prep_sock_cmd, which
            # is only a static inline function in the public header and has no compiled definition
            # in the FFI shared library. GNU ld merely warns about such undefined version-script
            # symbols, but lld 17+ defaults to --no-undefined-version and turns it into a hard
            # error. We do not use the FFI library, so allow the undefined version symbol instead
            # of failing the link.
            flags.append('-Wl,--undefined-version')
        return flags

    def use_cppflags_env_var(self) -> bool:
        return True
