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

import os
from typing import Optional, Tuple, List

from build_definitions import (
    BUILD_TYPE_ASAN,
    BUILD_TYPE_TSAN,
    BUILD_TYPE_UNINSTRUMENTED
)
from yugabyte_db_thirdparty.custom_logging import log, fatal
from sys_detection import is_linux, is_macos
from yugabyte_db_thirdparty.util import (
    which_must_exist,
    YB_THIRDPARTY_DIR,
    add_path_entry,
    extract_major_version,
)
from yugabyte_db_thirdparty.devtoolset import validate_devtoolset_compiler_path
from yugabyte_db_thirdparty.linuxbrew import using_linuxbrew, get_linuxbrew_dir
from yugabyte_db_thirdparty.arch import get_target_arch

from compiler_identification import (
    CompilerIdentification, identify_compiler
)
from packaging.version import parse as parse_version

LOWEST_GCC_VERSION_STR = '7.0.0'


class CompilerChoice:
    compiler_family: str
    cc: Optional[str]
    cxx: Optional[str]
    c_compiler_or_wrapper: Optional[str]
    cxx_compiler_or_wrapper: Optional[str]
    compiler_prefix: Optional[str]
    compiler_suffix: str
    devtoolset: Optional[int]
    use_compiler_wrapper: bool
    use_ccache: bool
    cc_identification: Optional[CompilerIdentification]
    cxx_identification: Optional[CompilerIdentification]
    compiler_version_str: Optional[str]
    expected_major_compiler_version: Optional[int]

    def __init__(
            self,
            compiler_family: str,
            compiler_prefix: Optional[str],
            compiler_suffix: str,
            devtoolset: Optional[int],
            use_compiler_wrapper: bool,
            use_ccache: bool,
            expected_major_compiler_version: Optional[int]) -> None:
        assert compiler_family in ['gcc', 'clang']
        self.compiler_family = compiler_family
        self.compiler_prefix = compiler_prefix
        self.compiler_suffix = compiler_suffix
        self.devtoolset = devtoolset
        self.use_compiler_wrapper = use_compiler_wrapper
        self.use_ccache = use_ccache

        self.cc = None
        self.cxx = None
        self.c_compiler_or_wrapper = None
        self.cxx_compiler_or_wrapper = None

        self.cc_identification = None
        self.cxx_identification = None

        self.compiler_version_str = None

        self.expected_major_compiler_version = expected_major_compiler_version

        self.find_compiler()
        self.identify_compiler_version()

    def find_compiler(self) -> None:
        compilers: Tuple[str, str]
        if self.is_gcc():
            compilers = self.find_gcc()
        elif self.is_clang():
            compilers = self.find_clang()
        else:
            fatal("Unknown compiler family {}".format(self.compiler_family))
        assert len(compilers) == 2

        for compiler in compilers:
            if compiler is None or not os.path.exists(compiler):
                fatal("Compiler executable does not exist: {}".format(compiler))

        self.cc = compilers[0]
        self.validate_compiler_path(self.cc)
        self.cxx = compilers[1]
        self.validate_compiler_path(self.cxx)

    def validate_compiler_path(self, compiler_path: str) -> None:
        if not os.path.exists(compiler_path):
            raise IOError("Compiler does not exist: %s" % compiler_path)

        if self.devtoolset:
            validate_devtoolset_compiler_path(compiler_path, self.devtoolset)

    def get_c_compiler(self) -> str:
        assert self.cc is not None
        return self.cc

    def get_cxx_compiler(self) -> str:
        assert self.cxx is not None
        return self.cxx

    def get_c_compiler_or_wrapper(self) -> str:
        assert self.c_compiler_or_wrapper is not None
        return self.c_compiler_or_wrapper

    def get_cxx_compiler_or_wrapper(self) -> str:
        assert self.cxx_compiler_or_wrapper is not None
        return self.cxx_compiler_or_wrapper

    def find_gcc(self) -> Tuple[str, str]:
        return self._do_find_gcc('gcc', 'g++')

    def _do_find_gcc(self, c_compiler: str, cxx_compiler: str) -> Tuple[str, str]:
        if using_linuxbrew():
            gcc_dir = get_linuxbrew_dir()
            assert gcc_dir is not None
        elif self.compiler_prefix:
            gcc_dir = self.compiler_prefix
        else:
            c_compiler_path = which_must_exist(c_compiler)
            cxx_compiler_path = which_must_exist(cxx_compiler)
            return c_compiler_path, cxx_compiler_path

        gcc_bin_dir = os.path.join(gcc_dir, 'bin')

        if not os.path.isdir(gcc_bin_dir):
            fatal("Directory {} does not exist".format(gcc_bin_dir))

        return (os.path.join(gcc_bin_dir, 'gcc') + self.compiler_suffix,
                os.path.join(gcc_bin_dir, 'g++') + self.compiler_suffix)

    def find_clang(self) -> Tuple[str, str]:
        clang_prefix: Optional[str] = None
        if self.compiler_prefix:
            clang_prefix = self.compiler_prefix
        else:
            candidate_dirs = [
                os.path.join(YB_THIRDPARTY_DIR, 'clang-toolchain'),
                '/usr'
            ]
            for dir in candidate_dirs:
                bin_dir = os.path.join(dir, 'bin')
                if os.path.exists(os.path.join(bin_dir, 'clang' + self.compiler_suffix)):
                    clang_prefix = dir
                    break
            if clang_prefix is None:
                fatal("Failed to find clang at the following locations: {}".format(candidate_dirs))

        assert clang_prefix is not None
        clang_bin_dir = os.path.join(clang_prefix, 'bin')

        return (os.path.join(clang_bin_dir, 'clang') + self.compiler_suffix,
                os.path.join(clang_bin_dir, 'clang++') + self.compiler_suffix)

    def is_clang(self) -> bool:
        return self.compiler_family == 'clang'

    def is_gcc(self) -> bool:
        return self.compiler_family == 'gcc'

    def is_linux_clang(self) -> bool:
        return is_linux() and self.is_clang()

    def set_compiler(self, use_compiler_wrapper: bool) -> None:
        self.use_compiler_wrapper = use_compiler_wrapper

        self.find_compiler()

        c_compiler = self.get_c_compiler()
        cxx_compiler = self.get_cxx_compiler()

        if self.use_compiler_wrapper:
            os.environ['YB_THIRDPARTY_REAL_C_COMPILER'] = c_compiler
            os.environ['YB_THIRDPARTY_REAL_CXX_COMPILER'] = cxx_compiler
            os.environ['YB_THIRDPARTY_USE_CCACHE'] = '1' if self.use_ccache else '0'

            python_scripts_dir = os.path.join(YB_THIRDPARTY_DIR, 'python', 'yugabyte_db_thirdparty')
            self.c_compiler_or_wrapper = os.path.join(python_scripts_dir, 'compiler_wrapper_cc.py')
            self.cxx_compiler_or_wrapper = os.path.join(
                python_scripts_dir, 'compiler_wrapper_cxx.py')
        else:
            self.c_compiler_or_wrapper = c_compiler
            self.cxx_compiler_or_wrapper = cxx_compiler

        os.environ['CC'] = self.c_compiler_or_wrapper
        os.environ['CXX'] = self.cxx_compiler_or_wrapper

        self.identify_compiler_version()

        log(f"C compiler: {self.cc_identification}")
        log(f"C++ compiler: {self.cxx_identification}")
        log(f"{'Using' if self.use_compiler_wrapper else 'Not using'} compiler wrapper")

        if self.expected_major_compiler_version:
            self.check_compiler_major_version()

    @staticmethod
    def _ensure_compiler_is_acceptable(compiler_identification: CompilerIdentification) -> None:
        if (compiler_identification.family == 'gcc' and
                compiler_identification.parsed_version < parse_version(LOWEST_GCC_VERSION_STR)):
            raise AssertionError(
                f"GCC version is too old: {compiler_identification}; "
                f"required at least {LOWEST_GCC_VERSION_STR}")

    def identify_compiler_version(self) -> None:
        c_compiler = self.get_c_compiler()
        cxx_compiler = self.get_cxx_compiler()

        self.cc_identification = identify_compiler(c_compiler)
        self.cxx_identification = identify_compiler(cxx_compiler)
        if not self.cc_identification.is_compatible_with(self.cxx_identification):
            raise RuntimeError(
                "C compiler and C++ compiler look incompatible. "
                f"C compiler: {self.cc_identification}, "
                f"C++ compiler: {self.cxx_identification}, "
            )

        self._ensure_compiler_is_acceptable(self.cc_identification)
        self._ensure_compiler_is_acceptable(self.cxx_identification)
        if self.cc_identification.version_str != self.cxx_identification.version_str:
            raise ValueError(
                "Different C and C++ compiler versions: %s vs %s",
                self.cc_identification.version_str,
                self.cxx_identification.version_str)
        self.compiler_version_str = self.cc_identification.version_str

    def get_llvm_version_str(self) -> str:
        assert self.is_clang()
        assert self.compiler_version_str is not None
        return self.compiler_version_str

    def get_compiler_major_version(self) -> int:
        assert self.compiler_version_str is not None
        return extract_major_version(self.compiler_version_str)

    def get_llvm_major_version(self) -> Optional[int]:
        if not self.is_clang():
            return None
        return extract_major_version(self.get_llvm_version_str())

    def is_llvm_major_version_at_least(self, lower_bound: int) -> bool:
        llvm_major_version = self.get_llvm_major_version()
        if llvm_major_version is None:
            raise ValueError("Expected compiler family to be 'clang'")
        return llvm_major_version >= lower_bound

    def get_gcc_major_version(self) -> Optional[int]:
        if self.compiler_family != 'gcc':
            return None
        assert self.compiler_version_str is not None
        return extract_major_version(self.compiler_version_str)

    def check_compiler_major_version(self) -> None:
        assert self.expected_major_compiler_version is not None
        actual_major_version = self.get_compiler_major_version()
        if actual_major_version != self.expected_major_compiler_version:
            raise ValueError(
                "Expected the C/C++ compiler major version to be %d, found %d. "
                "Full compiler version string: %s. "
                "Compiler type: %s. C compiler: %s. C++ compiler: %s" % (
                    self.expected_major_compiler_version,
                    actual_major_version,
                    self.compiler_version_str,
                    self.compiler_family,
                    self.cc_identification,
                    self.cxx_identification
                ))

    def using_clang(self) -> bool:
        assert self.compiler_family is not None
        return self.compiler_family == 'clang'

    def using_gcc(self) -> bool:
        assert self.compiler_family is not None
        return self.compiler_family == 'gcc'

    def get_compiler_family_and_version(self) -> str:
        return '%s%d' % (self.compiler_family, self.get_compiler_major_version())

    def get_build_type_components(
            self, lto_type: Optional[str], with_arch: bool) -> List[str]:
        """
        Returns a list of components that can be used to generate e.g. subdirectory names inside
        the "build" and "installed" directories, or the log prefix used when building a dependency.
        """
        components = [self.get_compiler_family_and_version()]
        if using_linuxbrew():
            components.append('linuxbrew')
        if lto_type is not None:
            components.append('%s-lto' % lto_type)
        if with_arch:
            components.append(get_target_arch())
        return components
