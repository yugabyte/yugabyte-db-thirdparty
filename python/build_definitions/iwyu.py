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

import os
import subprocess

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa

from typing import Optional


# IWYU pins to Clang's internal (unstable) APIs, so each release targets exactly one Clang major
# version. The version is therefore resolved from the toolchain's Clang at build time (see
# dependency_version) rather than hard-coded, so a single thirdparty commit can build IWYU for
# multiple Clang versions. Add an entry (and its checksum) when adding support for a new Clang.
IWYU_VERSION_FOR_CLANG_MAJOR = {
    19: '0.23',
    21: '0.25',
}


class IncludeWhatYouUseDependency(Dependency):
    """
    include-what-you-use (IWYU): a Clang-based tool that analyzes #include usage. It is shipped as a
    build-time host tool (not linked into YugabyteDB), so it is built once in the
    CXX_UNINSTRUMENTED group, like patchelf.
    """
    def __init__(self) -> None:
        super(IncludeWhatYouUseDependency, self).__init__(
            name='iwyu',
            version=None,  # resolved from the Clang major version at build time
            url_pattern='https://github.com/include-what-you-use/include-what-you-use/'
                        'archive/refs/tags/{0}.tar.gz',
            # The upstream tarball unpacks to include-what-you-use-<version>; name the archive to
            # match (the source dir is still renamed to iwyu-<version> on extraction).
            archive_name_prefix='include-what-you-use',
            build_group=BuildGroup.CXX_UNINSTRUMENTED)
        # IWYU's LLVM_LINK_COMPONENTS omits TargetParser, which provides
        # llvm::sys::getDefaultTargetTriple(); needed because we link LLVM's per-component shared
        # dylibs, which don't pull transitive component deps. See the patch for details. The block
        # it patches is identical across the IWYU releases we build, so one patch covers all.
        self.patches = ['iwyu-add-targetparser-link-component.patch']

    def dependency_version(self, builder: BuilderInterface) -> str:
        compiler_choice = builder.compiler_choice
        if not compiler_choice.is_llvm_installer_clang():
            raise RuntimeError(
                'include-what-you-use can only be built with an LLVM-installer Clang toolchain')
        major: Optional[int] = compiler_choice.get_llvm_major_version()
        version = IWYU_VERSION_FOR_CLANG_MAJOR.get(major) if major is not None else None
        if version is None:
            raise RuntimeError(
                'No include-what-you-use version configured for Clang major version %s; add one to '
                'IWYU_VERSION_FOR_CLANG_MAJOR in build_definitions/iwyu.py' % (major,))
        return version

    def build(self, builder: BuilderInterface) -> None:
        # IWYU links against the LLVM/Clang libraries of the toolchain we are building with. The C
        # compiler lives at <llvm_root>/bin/clang, so two dirname() calls give the toolchain root
        # that holds lib/cmake/llvm and lib/cmake/clang for find_package(LLVM)/find_package(Clang).
        llvm_root = os.path.dirname(os.path.dirname(builder.compiler_choice.get_c_compiler()))

        builder.build_with_cmake(
            self,
            shared_and_static=False,
            extra_cmake_args=[
                '-DCMAKE_BUILD_TYPE=Release',
                '-DCMAKE_PREFIX_PATH=' + llvm_root,
                # IWYU includes LLVM's HandleLLVMOptions, whose CheckCompilerVersion runs a
                # libstdc++ minimum-version probe unless told we use libc++. The thirdparty build
                # uses libc++ (-stdlib=libc++ -nostdinc++), so declare it to skip that probe (which
                # otherwise fails and aborts the configure).
                '-DLLVM_ENABLE_LIBCXX=ON',
            ])

        # build_with_cmake installs into the dependency's install prefix. Verify the tool landed
        # there (mirrors patchelf's post-build existence check).
        install_prefix = self.get_install_prefix(builder)
        iwyu_path = os.path.join(install_prefix, 'bin', 'include-what-you-use')
        if os.path.exists(iwyu_path):
            log("include-what-you-use installed at %s", iwyu_path)
        else:
            raise IOError("include-what-you-use was not installed at %s" % iwyu_path)

        self.fix_macos_libcxx_rpath(install_prefix, iwyu_path)

    def fix_macos_libcxx_rpath(self, install_prefix: str, iwyu_path: str) -> None:
        """
        On macOS, drop the thirdparty libc++ rpath from the IWYU binary so it resolves libc++ from
        the Clang toolchain at runtime.

        IWYU links the toolchain's LLVM/Clang dylibs, which were built against the toolchain's
        libc++ (libc++abi merged into libc++.1.0.dylib). The thirdparty libc++ keeps libc++abi as a
        separate dylib, so it lacks symbols the toolchain dylibs expect from libc++.1.0.dylib (e.g.
        __cxxabiv1::__si_class_type_info vtable), causing a dyld "Symbol not found" at startup. The
        thirdparty libcxx/lib rpath is listed first, so dyld loads the wrong libc++. Removing that
        rpath makes dyld fall through to the toolchain lib dir (the only other rpath that has
        libc++.1.0.dylib), which has the merged symbols. This is a host tool, so using the toolchain
        libc++ at runtime is fine. Not needed on Linux: ELF flat-namespace resolution finds the
        symbol in the separate libc++abi regardless of which library declares it.
        """
        if not is_macos():
            return
        libcxx_rpath = os.path.join(install_prefix, 'libcxx', 'lib')
        rpaths = subprocess.check_output(['otool', '-l', iwyu_path]).decode('utf-8')
        if libcxx_rpath not in rpaths:
            log("libcxx rpath %s not present in %s, nothing to fix", libcxx_rpath, iwyu_path)
            return
        log("Removing thirdparty libc++ rpath %s from %s", libcxx_rpath, iwyu_path)
        subprocess.check_call(['install_name_tool', '-delete_rpath', libcxx_rpath, iwyu_path])
