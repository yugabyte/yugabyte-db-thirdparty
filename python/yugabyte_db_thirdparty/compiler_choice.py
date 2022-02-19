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

from compiler_identification import (
    CompilerIdentification, identify_compiler
)
from packaging.version import parse as parse_version

LOWEST_GCC_VERSION_STR = '7.0.0'


class CompilerChoice:
    compiler_type: str
    cc: Optional[str]
    cxx: Optional[str]
    c_compiler_or_wrapper: Optional[str]
    cxx_compiler_or_wrapper: Optional[str]
    single_compiler_type: Optional[str]
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
            single_compiler_type: Optional[str],
            compiler_prefix: Optional[str],
            compiler_suffix: str,
            devtoolset: Optional[int],
            use_compiler_wrapper: bool,
            use_ccache: bool,
            expected_major_compiler_version: Optional[int]) -> None:
        self.single_compiler_type = single_compiler_type
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
        if single_compiler_type is not None:
            self.set_compiler(self.single_compiler_type)

    def detect_clang_version(self) -> None:
        """
        Detects Clang version when the only compiler we are using is Clang. This is needed so we can
        use versions of components that are part of LLVM's repository that match the version of
        Clang.
        """
        if is_linux() and self.single_compiler_type == 'clang':
            self.find_compiler_by_type(self.single_compiler_type)
            self._identify_compiler_version()

    def finish_initialization(self) -> None:
        self.detect_clang_version()

    def find_compiler_by_type(self, compiler_type: str) -> None:
        compilers: Tuple[str, str]
        if compiler_type == 'gcc':
            if self.use_only_clang():
                raise ValueError('Not allowed to use GCC')
            compilers = self.find_gcc()
        elif compiler_type == 'clang':
            if self.use_only_gcc():
                raise ValueError('Not allowed to use Clang')
            compilers = self.find_clang()
        else:
            fatal("Unknown compiler type {}".format(compiler_type))
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

    def building_with_clang(self, build_type: str) -> bool:
        """
        Returns true if we are using clang to build current build_type.
        """
        if self.use_only_clang():
            return True
        if self.use_only_gcc():
            return False

        return build_type in [
            BUILD_TYPE_ASAN,
            BUILD_TYPE_TSAN,
        ]

    def will_need_clang(self, build_type: str) -> bool:
        """
        Returns true if we will need Clang to complete the full thirdparty build type requested by
        the user.
        """
        if self.use_only_gcc():
            return False
        return build_type != BUILD_TYPE_UNINSTRUMENTED

    def use_only_clang(self) -> bool:
        return is_macos() or self.single_compiler_type == 'clang'

    def use_only_gcc(self) -> bool:
        return self.devtoolset is not None or self.single_compiler_type == 'gcc'

    def is_linux_clang1x(self) -> bool:
        llvm_major_version: Optional[int] = self.get_llvm_major_version()
        return (
            not is_macos() and
            self.single_compiler_type == 'clang' and
            llvm_major_version is not None and
            llvm_major_version >= 10
        )

    def set_compiler(self, compiler_type: str) -> None:
        if is_macos():
            if compiler_type != 'clang':
                raise ValueError(
                    "Cannot set compiler type to %s on macOS, only clang is supported" %
                    compiler_type)
            self.compiler_type = 'clang'
        else:
            self.compiler_type = compiler_type

        self.find_compiler_by_type(compiler_type)

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

        self._identify_compiler_version()

        log(f"C compiler: {self.cc_identification}")
        log(f"C++ compiler: {self.cxx_identification}")

        if self.expected_major_compiler_version:
            self.check_compiler_major_version()

    @staticmethod
    def _ensure_compiler_is_acceptable(compiler_identification: CompilerIdentification) -> None:
        if (compiler_identification.family == 'gcc' and
                compiler_identification.parsed_version < parse_version(LOWEST_GCC_VERSION_STR)):
            raise AssertionError(
                f"GCC version is too old: {compiler_identification}; "
                f"required at least {LOWEST_GCC_VERSION_STR}")

    def _identify_compiler_version(self) -> None:
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
        assert self.single_compiler_type == 'clang', \
            f"Expected the compiler type to be 'clang' only but found '{self.single_compiler_type}'"
        assert self.compiler_version_str is not None
        return self.compiler_version_str

    def get_compiler_major_version(self) -> int:
        assert self.compiler_version_str is not None
        return extract_major_version(self.compiler_version_str)

    def get_llvm_major_version(self) -> Optional[int]:
        if self.single_compiler_type is None or self.single_compiler_type == 'gcc':
            return None
        return extract_major_version(self.get_llvm_version_str())

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
                    self.compiler_type,
                    self.cc_identification,
                    self.cxx_identification
                ))
