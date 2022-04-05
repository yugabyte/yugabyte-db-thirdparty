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

from typing import List, Optional, Callable, TYPE_CHECKING

from yugabyte_db_thirdparty.file_system_layout import FileSystemLayout

if TYPE_CHECKING:
    from .dependency import Dependency
    from .compiler_choice import CompilerChoice


class BuilderInterface:
    """
    The Builder interface exposed to Dependency instances.
    """

    prefix: str
    compiler_flags: List[str]
    c_flags: List[str]
    cxx_flags: List[str]
    compiler_type: str
    prefix_lib: str
    prefix_bin: str
    ld_flags: List[str]
    shared_lib_suffix: str
    tp_installed_common_dir: str
    prefix_include: str
    tp_dir: str
    build_type: str
    compiler_choice: 'CompilerChoice'
    fs_layout: FileSystemLayout
    lto_type: Optional[str]

    def build_with_configure(
            self,
            log_prefix: str,
            extra_args: List[str] = [],
            configure_cmd: List[str] = ['./configure'],
            install: List[str] = ['install'],
            run_autogen: bool = False,
            autoconf: bool = False,
            src_subdir_name: Optional[str] = None,
            post_configure_action: Optional[Callable] = None) -> None:
        raise NotImplementedError()

    def build_with_cmake(
            self,
            dep: 'Dependency',
            extra_args: List[str] = [],
            use_ninja_if_available: bool = False,
            src_subdir_name: Optional[str] = None,
            extra_build_tool_args: List[str] = [],
            should_install: bool = True,
            install_targets: List[str] = [],
            shared_and_static: bool = False) -> None:
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

    def get_install_prefix_with_qualifier(self, qualifier: Optional[str]) -> str:
        raise NotImplementedError()
