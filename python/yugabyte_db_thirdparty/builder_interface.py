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

from re import Pattern
from typing import List, Optional, Callable, Any, TYPE_CHECKING

from yugabyte_db_thirdparty.file_system_layout import FileSystemLayout
from build_definitions import BuildType

if TYPE_CHECKING:
    from .dependency import Dependency
    from .compiler_choice import CompilerChoice

# Some of the default arguments below are shared between different methods.

# -------------------------------------------------------------------------------------------------
# Default arguments for build_with_make
# -------------------------------------------------------------------------------------------------

DEFAULT_EXTRA_MAKE_ARGS: List[str] = []
DEFAULT_INSTALL_TARGETS: List[str] = ['install']
DEFAULT_MAKE_SPECIFY_PREFIX = False

# Could be a custom variable name in some cases, e.g. "DESTDIR".
DEFAULT_MAKE_PREFIX_VAR = 'PREFIX'

# -------------------------------------------------------------------------------------------------
# Default arguments for build_with_configure
# -------------------------------------------------------------------------------------------------

DEFAULT_EXTRA_CONFIGURE_ARGS: List[str] = []
DEFAULT_CONFIGURE_CMD: List[str] = ['./configure']
DEFAULT_RUN_AUTOGEN = False
DEFAULT_RUN_AUTORECONF = False
DEFAULT_SRC_SUBDIR_NAME: Optional[str] = None

# -------------------------------------------------------------------------------------------------
# Default arguments for build_with_cmake
# -------------------------------------------------------------------------------------------------

DEFAULT_EXTRA_CMAKE_ARGS: List[str] = []
DEFAULT_USE_NINJA_IF_AVAILABLE = True
DEFAULT_EXTRA_MAKE_OR_NINJA_ARGS: List[str] = []
DEFAULT_CMAKE_SHOULD_INSTALL = True
DEFAULT_CMAKE_BUILD_SHARED_AND_STATIC = False


class BuilderInterface:
    """
    The Builder interface exposed to Dependency instances.
    """

    prefix: str

    # Flags
    compiler_flags: List[str]
    c_flags: List[str]
    cxx_flags: List[str]
    preprocessor_flags: List[str]
    ld_flags: List[str]

    compiler_family: str
    prefix_lib: str
    prefix_bin: str
    shared_lib_suffix: str
    tp_installed_common_dir: str
    prefix_include: str
    tp_dir: str
    build_type: BuildType
    compiler_choice: 'CompilerChoice'
    fs_layout: FileSystemLayout
    lto_type: Optional[str]

    # For the build_with_... functions below, please make sure their signatures match those in
    # builder.py, and that all default arguments are specified as DEFAULT_... constants defined
    # in this module.

    def build_with_make(
            self,
            dep: 'Dependency',
            extra_make_args: List[str] = DEFAULT_EXTRA_MAKE_ARGS,
            install_targets: List[str] = DEFAULT_INSTALL_TARGETS,
            specify_prefix: bool = DEFAULT_MAKE_SPECIFY_PREFIX,
            prefix_var: str = DEFAULT_MAKE_PREFIX_VAR) -> None:
        raise NotImplementedError()

    def build_with_configure(
            self,
            dep: 'Dependency',
            extra_configure_args: List[str] = DEFAULT_EXTRA_CONFIGURE_ARGS,
            extra_make_args: List[str] = DEFAULT_EXTRA_MAKE_ARGS,
            configure_cmd: List[str] = DEFAULT_CONFIGURE_CMD,
            install_targets: List[str] = DEFAULT_INSTALL_TARGETS,
            run_autogen: bool = DEFAULT_RUN_AUTOGEN,
            run_autoreconf: bool = DEFAULT_RUN_AUTORECONF,
            src_subdir_name: Optional[str] = DEFAULT_SRC_SUBDIR_NAME,
            post_configure_action: Optional[Callable] = None) -> None:
        raise NotImplementedError()

    def build_with_cmake(
            self,
            dep: 'Dependency',
            extra_cmake_args: List[str] = DEFAULT_EXTRA_CMAKE_ARGS,
            use_ninja_if_available: bool = DEFAULT_USE_NINJA_IF_AVAILABLE,
            src_subdir_name: Optional[str] = DEFAULT_SRC_SUBDIR_NAME,
            extra_build_tool_args: List[str] = DEFAULT_EXTRA_MAKE_OR_NINJA_ARGS,
            should_install: bool = DEFAULT_CMAKE_SHOULD_INSTALL,
            shared_and_static: bool = DEFAULT_CMAKE_BUILD_SHARED_AND_STATIC) -> None:
        raise NotImplementedError()

    def build_with_bazel(
            self,
            dep: 'Dependency',
            verbose_output: bool = False,
            should_clean: bool = False,
            targets: List[str] = []) -> None:
        raise NotImplementedError()

    def install_bazel_build_output(
            self,
            dep: 'Dependency',
            src_file: str,
            dest_file: str,
            src_folder: str,
            is_shared: bool) -> None:
        raise NotImplementedError()

    def log_prefix(self, dep: 'Dependency') -> str:
        raise NotImplementedError()

    def prepend_rpath(self, path: str) -> None:
        # TODO: should dependencies really be calling this?
        raise NotImplementedError()

    def cmake_build_type_for_test_only_dependencies(self) -> str:
        raise NotImplementedError()

    def get_openssl_related_cmake_args(self) -> List[str]:
        raise NotImplementedError()

    def add_checked_flag(self, flags: List[str], flag: str) -> None:
        raise NotImplementedError()

    def get_openssl_dir(self) -> str:
        raise NotImplementedError()

    def is_release_build(self) -> bool:
        raise NotImplementedError()

    def get_common_cmake_flag_args(self, dep: 'Dependency') -> List[str]:
        raise NotImplementedError()

    def get_install_prefix(self) -> str:
        raise NotImplementedError()

    def log_output(
            self,
            prefix: str,
            args: List[Any],
            disallowed_pattern: Optional[Pattern] = None) -> None:
        raise NotImplementedError()

    def copy_include_files(
            self,
            dep: 'Dependency',
            rel_src_include_path: str,
            dest_include_path: str) -> None:
        raise NotImplementedError()
