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

import argparse
import hashlib
import json
import os
import platform
import subprocess
import stat
import time
import re

from re import Pattern

from typing import Optional, List, Set, Tuple, Dict, Any, Callable

from sys_detection import is_macos, is_linux
from pathlib import Path

from build_definitions import (
    BUILD_GROUP_COMMON,
    BUILD_GROUP_INSTRUMENTED,
    BUILD_TYPE_ASAN,
    BUILD_TYPE_COMMON,
    BUILD_TYPE_TSAN,
    BUILD_TYPE_UNINSTRUMENTED,
    BUILD_TYPES,
    get_build_def_module,
    get_deps_from_module_names,
)
from yugabyte_db_thirdparty.builder_helpers import (
    format_cmake_args_for_log,
    get_make_parallelism,
    get_rpath_flag,
    log_and_set_env_var_to_list,
    PLACEHOLDER_RPATH,
)
from yugabyte_db_thirdparty.builder_helpers import is_ninja_available
from yugabyte_db_thirdparty.builder_interface import BuilderInterface
from yugabyte_db_thirdparty.cmd_line_args import parse_cmd_line_args
from yugabyte_db_thirdparty.compiler_choice import CompilerChoice
from yugabyte_db_thirdparty.custom_logging import (
    colored_log,
    fatal,
    heading,
    log,
    log_output_internal,
    SEPARATOR,
    YELLOW_COLOR,
)
from yugabyte_db_thirdparty.dependency import Dependency
from yugabyte_db_thirdparty.devtoolset import activate_devtoolset
from yugabyte_db_thirdparty.download_manager import DownloadManager
from yugabyte_db_thirdparty.env_helpers import write_env_vars
from yugabyte_db_thirdparty.string_util import indent_lines
from yugabyte_db_thirdparty.arch import (
    get_arch_switch_cmd_prefix,
    get_target_arch,
    get_other_macos_arch,
    add_homebrew_to_path,
)
from yugabyte_db_thirdparty.util import (
    assert_dir_exists,
    assert_list_contains,
    EnvVarContext,
    mkdir_if_missing,
    PushDir,
    read_file,
    remove_path,
    YB_THIRDPARTY_DIR,
    add_path_entry,
    shlex_join,
)
from yugabyte_db_thirdparty.file_system_layout import FileSystemLayout
from yugabyte_db_thirdparty.toolchain import Toolchain, ensure_toolchains_installed
from yugabyte_db_thirdparty.clang_util import (
    get_clang_library_dir,
    get_clang_include_dir,
    create_llvm_tool_dir,
)
from yugabyte_db_thirdparty.macos import get_min_supported_macos_version
from yugabyte_db_thirdparty.linuxbrew import get_linuxbrew_dir, using_linuxbrew, set_linuxbrew_dir
from yugabyte_db_thirdparty.constants import (
    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_APPEND,
    COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_REMOVE,
)


ASAN_COMPILER_FLAGS = [
    '-fsanitize=address',
    '-fsanitize=undefined',
    '-DADDRESS_SANITIZER',
]

ASAN_LD_FLAGS = [
    '-Wl,--allow-shlib-undefined',
    '-Wl,--unresolved-symbols=ignore-all'
]

TSAN_COMPILER_FLAGS = [
    '-fsanitize=thread',
    '-DTHREAD_SANITIZER',
]

# https://github.com/aws/aws-graviton-getting-started/blob/main/c-c++.md
GRAVITON_COMPILER_FLAGS = [
    '-march=armv8.2-a+fp16+rcpc+dotprod+crypto',
    '-mtune=neoverse-n1',
    '-mno-outline-atomics',
]

# We create a file named like this in each dependency's build directory, with all the relevant
# environment variables that we set.
DEPENDENCY_ENV_FILE_NAME = 'yb_dependency_env.sh'

# If this pattern appears, we should use the CPPFLAGS environment variable for this dependency
DISALLOWED_CONFIGURE_OUTPUT_RE = re.compile(
    '(C|CXX)FLAGS should only be used to specify C compiler flags, not include directories[.]')


def extend_lists(lists: List[List[str]], to_add: List[str]) -> None:
    for list_to_extend in lists:
        list_to_extend.extend(to_add.copy())


class Builder(BuilderInterface):
    args: argparse.Namespace

    # TODO: move flag management out from here into a separate class.

    # Linker flags.
    ld_flags: List[str]

    assembler_flags: List[str]

    executable_only_ld_flags: List[str]

    # These flags apply to both C and C++ compilers. Do not add preprocessor flags (e.g. include
    # directories, system include directories, etc.) here.
    compiler_flags: List[str]

    # Based on the dependency, we either set CPPFLAGS based on this, or add them to CFLAGS/CXXFLAGS.
    # For CMake dependencies, we always add them to compiler flags.
    preprocessor_flags: List[str]

    # Flags specific for C and C++ compilers.
    c_flags: List[str]
    cxx_flags: List[str]

    libs: List[str]
    additional_allowed_shared_lib_paths: Set[str]
    download_manager: DownloadManager
    compiler_choice: CompilerChoice
    fs_layout: FileSystemLayout
    fossa_deps: List[Any]
    toolchain: Optional[Toolchain]
    remote_build: bool

    lto_type: Optional[str]
    selected_dependencies: List[Dependency]

    """
    This class manages the overall process of building third-party dependencies, including the set
    of dependencies to build, build types, and the directories to install dependencies.
    """
    def __init__(self) -> None:
        self.linuxbrew_dir = None
        self.additional_allowed_shared_lib_paths = set()

        self.toolchain = None
        self.fossa_deps = []
        self.lto_type = None

    def install_toolchains(self) -> None:
        toolchains = ensure_toolchains_installed(
            self.download_manager, self.args.toolchain.split('_'))

        # We expect at most one Linuxbrew toolchain to be specified (handled by set_linuxbrew_dir).
        for toolchain in toolchains:
            if toolchain.toolchain_type == 'linuxbrew':
                set_linuxbrew_dir(toolchain.toolchain_root)

        if len(toolchains) == 1:
            self.toolchain = toolchains[0]
            return
        if len(toolchains) != 2:
            raise ValueError("Unsupported combination of toolchains: %s" % self.args.toolchain)
        if not toolchains[0].toolchain_type.startswith('llvm'):
            raise ValueError(
                "For a combination of toolchains, the first one must be an LLVM one, got: %s" %
                toolchains[0].toolchain_type)
        self.toolchain = toolchains[0]
        if toolchains[1].toolchain_type != 'linuxbrew':
            raise ValueError(
                "For a combination of toolchains, the second one must be Linuxbrew, got: %s" %
                toolchains[1].toolchain_type)

    def determine_compiler_family_and_prefix(self) -> Tuple[str, Optional[str]]:
        compiler_family: Optional[str] = None
        compiler_prefix: Optional[str] = None
        if self.args.toolchain:
            self.install_toolchains()
            assert self.toolchain is not None  # install_toolchains guarantees this.
            compiler_prefix = self.toolchain.toolchain_root
            self.toolchain.write_url_and_path_files()
            if self.args.toolchain.startswith('llvm'):
                compiler_family = 'clang'
        elif self.args.devtoolset:
            compiler_family = 'gcc'
        elif self.args.compiler_prefix:
            compiler_prefix = self.args.compiler_prefix

        if is_macos():
            if compiler_family is None:
                compiler_family = 'clang'
            elif compiler_family != 'clang':
                raise ValueError("Only clang compiler family is supported on macOS")

        if self.args.compiler_family is not None:
            if compiler_family is None:
                compiler_family = self.args.compiler_family
            elif compiler_family != self.args.compiler_family:
                raise ValueError("Compiler type specified on the command line is %s, "
                                 "but automatically determined as %s" % (self.args.compiler_family,
                                                                         compiler_family))

        if compiler_family is None:
            raise ValueError(
                "Could not determine compiler family. Use --compiler-family to disambiguate.")
        return compiler_family, compiler_prefix

    def parse_args(self) -> None:
        self.args = parse_cmd_line_args()

        self.remote_build = self.args.remote_build_server and self.args.remote_build_dir
        if self.remote_build:
            return

        if self.args.make_parallelism:
            os.environ['YB_MAKE_PARALLELISM'] = str(self.args.make_parallelism)

        self.fs_layout = FileSystemLayout()

        self.download_manager = DownloadManager(
            should_add_checksum=self.args.add_checksum,
            download_dir=self.fs_layout.tp_download_dir)

        compiler_family, compiler_prefix = self.determine_compiler_family_and_prefix()

        if self.args.devtoolset is not None:
            activate_devtoolset(self.args.devtoolset)
        self.compiler_choice = CompilerChoice(
            compiler_family=compiler_family,
            compiler_prefix=compiler_prefix,
            compiler_suffix=self.args.compiler_suffix,
            devtoolset=self.args.devtoolset,
            use_compiler_wrapper=False,
            use_ccache=self.args.use_ccache,
            expected_major_compiler_version=self.args.expected_major_compiler_version
        )
        llvm_major_version: Optional[int] = self.compiler_choice.get_llvm_major_version()
        if llvm_major_version:
            if using_linuxbrew():
                log("Automatically enabling compiler wrapper for a Clang Linuxbrew-targeting build")
                log("Disallowing the use of headers in /usr/include")
                os.environ['YB_DISALLOWED_INCLUDE_DIRS'] = '/usr/include'
                self.args.use_compiler_wrapper = True
            if llvm_major_version >= 13:
                log("Automatically enabling compiler wrapper for Clang major version 13 or higher")
                self.args.use_compiler_wrapper = True
        self.compiler_choice.use_compiler_wrapper = self.args.use_compiler_wrapper

        self.lto_type = self.args.lto

    def finish_initialization(self) -> None:
        self.fs_layout.finish_initialization(
            per_build_subdirs=(
                True if self.args.per_build_dirs else
                (False if self.args.no_per_build_dirs else None)
            ),
            compiler_choice=self.compiler_choice,
            lto_type=self.args.lto)
        self.populate_dependencies()
        self.select_dependencies_to_build()
        self.compiler_choice.set_compiler(use_compiler_wrapper=False)

    def populate_dependencies(self) -> None:
        # We have to use get_build_def_module to access submodules of build_definitions,
        # otherwise MyPy gets confused.

        self.dependencies = get_deps_from_module_names([
            # Avoiding a name collision with the standard zlib module, hence "zlib_dependency".
            'zlib_dependency',
            'lz4',
            'openssl',
            'libev',
            'rapidjson',
            'squeasel',
            'curl',
            'hiredis',
            'cqlsh',
            'flex',
            'bison',
            'openldap',
            'redis_cli',
            'wyhash',
        ])
        for dep in self.dependencies:
            if dep.build_group != BUILD_GROUP_COMMON:
                raise ValueError(
                    "Expected the initial group of dependencies to all be in the common build "
                    f"group, found: {dep.build_group} for dependency {dep.name}")

        if is_linux():
            self.dependencies += [
                get_build_def_module('libuuid').LibUuidDependency(),
            ]

            llvm_major_version: Optional[int] = self.compiler_choice.get_llvm_major_version()
            if (self.compiler_choice.is_clang() and
                    llvm_major_version is not None and llvm_major_version >= 10):
                if self.toolchain:
                    llvm_version_str = self.toolchain.get_llvm_version_str()
                else:
                    llvm_version_str = self.compiler_choice.get_llvm_version_str()

                self.dependencies.append(
                    get_build_def_module('llvm_libunwind').LlvmLibUnwindDependency(
                        version=llvm_version_str
                    ))
                libcxx_dep_module = get_build_def_module('llvm_libcxx')
                if llvm_major_version >= 13:
                    self.dependencies.append(
                        libcxx_dep_module.LibCxxWithAbiDependency(version=llvm_version_str))
                else:
                    # It is important that we build libc++abi first, and only then build libc++.
                    self.dependencies += [
                        libcxx_dep_module.LlvmLibCxxAbiDependency(version=llvm_version_str),
                        libcxx_dep_module.LlvmLibCxxDependency(version=llvm_version_str),
                    ]
            else:
                self.dependencies.append(get_build_def_module('libunwind').LibUnwindDependency())

            self.dependencies.append(get_build_def_module('libbacktrace').LibBacktraceDependency())

        self.dependencies += get_deps_from_module_names(
            # On macOS, flex, bison, and krb5 depend on gettext, and we don't want to use gettext
            # from Homebrew.
            # libunistring is required by gettext.
            (
                ['libunistring', 'gettext'] if is_macos() else []
            ) + [
                'ncurses',
            ] + (
                [] if is_macos() else ['libkeyutils', 'libverto', 'abseil', 'tcmalloc']
            ) + [
                'libedit',
                'icu4c',
                'protobuf',
                'crypt_blowfish',
                'boost',
                'gflags',
                'glog',
                'gperftools',
                'googletest',
                'snappy',
                'crcutil',
                'libcds',
                'libuv',
                'cassandra_cpp_driver',
                'krb5',
                'hdrhistogram',
                'otel_proto',
                'otel'
            ])

    def select_dependencies_to_build(self) -> None:
        self.selected_dependencies = []
        if self.args.dependencies:
            names = set([dep.name for dep in self.dependencies])
            for dep in self.args.dependencies:
                if dep not in names:
                    fatal("Unknown dependency name: %s. Valid dependency names:\n%s",
                          dep,
                          (" " * 4 + ("\n" + " " * 4).join(sorted(names))))
            for dep in self.dependencies:
                if dep.name in self.args.dependencies:
                    self.selected_dependencies.append(dep)
        elif self.args.skip:
            skipped = set(self.args.skip.split(','))
            log("Skipping dependencies: %s", sorted(skipped))
            self.selected_dependencies = []
            for dependency in self.dependencies:
                if dependency.name in skipped:
                    skipped.remove(dependency.name)
                else:
                    self.selected_dependencies.append(dependency)
            if skipped:
                raise ValueError("Unknown dependencies, cannot skip: %s" % sorted(skipped))
        else:
            self.selected_dependencies = self.dependencies

    def _setup_path(self) -> None:
        add_path_entry(os.path.join(self.fs_layout.tp_installed_common_dir, 'bin'))
        add_homebrew_to_path()
        if self.compiler_choice.is_linux_clang():
            llvm_tool_dir = self.fs_layout.get_llvm_tool_dir()
            if create_llvm_tool_dir(self.compiler_choice.get_c_compiler(), llvm_tool_dir):
                add_path_entry(llvm_tool_dir)

    def run(self) -> None:
        if is_macos() and get_target_arch() == 'x86_64':
            os.environ['MACOSX_DEPLOYMENT_TARGET'] = get_min_supported_macos_version()
        if self.args.clean or self.args.clean_downloads:
            self.fs_layout.clean(self.selected_dependencies, self.args.clean_downloads)
        self.prepare_out_dirs()
        self._setup_path()

        self.build_one_build_type(BUILD_TYPE_COMMON)
        build_types = [BUILD_TYPE_UNINSTRUMENTED]

        if (is_linux() and
                self.compiler_choice.is_clang() and
                not self.args.skip_sanitizers and
                not using_linuxbrew()):
            # We only support ASAN/TSAN builds on Clang, when not using Linuxbrew.
            if not self.args.skip_asan:
                build_types.append(BUILD_TYPE_ASAN)
            if not self.args.skip_tsan:
                build_types.append(BUILD_TYPE_TSAN)
        log(f"Full list of build types: {build_types}")

        for build_type in build_types:
            self.build_one_build_type(build_type)

        fossa_config_deps = {"remote-dependencies": self.fossa_deps}
        with open(os.path.join(YB_THIRDPARTY_DIR, 'fossa-deps.json'), 'w') as output_file:
            json.dump(fossa_config_deps, output_file, indent=2)

    def get_build_types(self) -> List[str]:
        return list(BUILD_TYPES)

    def prepare_out_dirs(self) -> None:
        build_types = self.get_build_types()
        dirs = [
            os.path.join(self.fs_layout.tp_installed_dir, build_type) for build_type in build_types
        ]
        libcxx_dirs = [os.path.join(dir_path, 'libcxx') for dir_path in dirs]
        for dir_path in dirs + libcxx_dirs:
            if self.args.verbose:
                log("Preparing output directory %s", dir_path)
            mkdir_if_missing(os.path.join(dir_path, 'bin'))
            lib_dir = os.path.join(dir_path, 'lib')
            mkdir_if_missing(lib_dir)
            mkdir_if_missing(os.path.join(dir_path, 'include'))
            # On some systems, autotools installs libraries to lib64 rather than lib. Fix this by
            # setting up lib64 as a symlink to lib. We have to do this step first to handle cases
            # where one third-party library depends on another.
            lib64_dir = os.path.join(dir_path, 'lib64')
            if os.path.exists(lib64_dir):
                if os.path.islink(lib64_dir):
                    continue
                remove_path(lib64_dir)
            os.symlink('lib', lib64_dir)

    def add_include_path(self, include_path: str) -> None:
        if self.args.verbose:
            log("Adding an include path: %s", include_path)
        cmd_line_arg = f'-I{include_path}'
        self.preprocessor_flags.append(cmd_line_arg)
        # Not adding to compiler_flags. We can add preprocessor flags to compiler flags when
        # building the dependency instead.

    def init_compiler_independent_flags(self, dep: Dependency) -> None:
        """
        Initialize compiler and linker flags for a particular build type. We try to limit this
        function to flags that will work for most compilers we are using, which include various
        versions of GCC and Clang.
        """
        self.preprocessor_flags = []
        self.ld_flags = []
        self.assembler_flags = []
        self.executable_only_ld_flags = []
        self.compiler_flags = []
        self.c_flags = []
        self.cxx_flags = []
        self.libs = []

        self.add_linuxbrew_flags()
        for include_dir_component in set([BUILD_TYPE_COMMON, self.build_type]):
            self.add_include_path(os.path.join(
                self.fs_layout.tp_installed_dir, include_dir_component, 'include'))
            self.add_lib_dir_and_rpath(os.path.join(
                self.fs_layout.tp_installed_dir, include_dir_component, 'lib'))

        self.compiler_flags += ['-fno-omit-frame-pointer', '-fPIC', '-O3', '-Wall']
        if is_linux():
            # On Linux, ensure we set a long enough rpath so we can change it later with chrpath,
            # patchelf, or a similar tool.
            self.add_rpath(PLACEHOLDER_RPATH)

            self.shared_lib_suffix = "so"

            # Currently linux/aarch64 build is optimized for Graviton2.
            if platform.uname().processor == 'aarch64':
                self.compiler_flags += GRAVITON_COMPILER_FLAGS

        elif is_macos():
            self.shared_lib_suffix = "dylib"

            # YugaByte builds with C++11, which on OS X requires using libc++ as the standard
            # library implementation. Some of the dependencies do not compile against libc++ by
            # default, so we specify it explicitly.
            self.cxx_flags.append("-stdlib=libc++")
            self.ld_flags += ["-lc++", "-lc++abi"]

            # Build for macOS Mojave or later. See https://bit.ly/37myHbk
            extend_lists(
                [self.compiler_flags, self.ld_flags, self.assembler_flags],
                ["-mmacosx-version-min=%s" % get_min_supported_macos_version()])

            self.ld_flags.append("-Wl,-headerpad_max_install_names")
        else:
            fatal("Unsupported platform: {}".format(platform.system()))

        self.cxx_flags.append('-frtti')

        if self.build_type == BUILD_TYPE_ASAN:
            self.compiler_flags += ASAN_COMPILER_FLAGS
            self.ld_flags += ASAN_LD_FLAGS

        if self.build_type == BUILD_TYPE_TSAN:
            self.compiler_flags += TSAN_COMPILER_FLAGS

    def add_linuxbrew_flags(self) -> None:
        if using_linuxbrew():
            lib_dir = os.path.join(get_linuxbrew_dir(), 'lib')
            self.ld_flags.append(" -Wl,-dynamic-linker={}".format(os.path.join(lib_dir, 'ld.so')))
            self.add_lib_dir_and_rpath(lib_dir)

    def add_lib_dir_and_rpath(self, lib_dir: str) -> None:
        if self.args.verbose:
            log("Adding a library directory and RPATH at the end of linker flags: %s", lib_dir)
        self.ld_flags.append("-L{}".format(lib_dir))
        self.add_rpath(lib_dir)

    def prepend_lib_dir_and_rpath(self, lib_dir: str) -> None:
        if self.args.verbose:
            log("Adding a library directory and RPATH at the front of linker flags: %s", lib_dir)
        self.ld_flags.insert(0, "-L{}".format(lib_dir))
        self.prepend_rpath(lib_dir)

    def add_rpath(self, path: str) -> None:
        log("Adding RPATH at the end of linker flags: %s", path)
        self.ld_flags.append(get_rpath_flag(path))
        self.additional_allowed_shared_lib_paths.add(path)

    def prepend_rpath(self, path: str) -> None:
        log("Adding RPATH at the front of linker flags: %s", path)
        self.ld_flags.insert(0, get_rpath_flag(path))
        self.additional_allowed_shared_lib_paths.add(path)

    def log_prefix(self, dep: Dependency) -> str:
        detail_components = self.compiler_choice.get_build_type_components(
                lto_type=self.lto_type, with_arch=False) + [self.build_type]
        return '{} ({})'.format(dep.name, ', '.join(detail_components))

    def check_current_dir(self) -> None:
        current_dir = os.path.realpath(os.getcwd())
        top_dir = os.path.realpath(YB_THIRDPARTY_DIR)
        if current_dir == top_dir:
            raise IOError(
                    "Dependency build is not allowed to run with the current directory being "
                    f"the top-level directory of yugabyte-db-thirdparty: {YB_THIRDPARTY_DIR}")

    def build_with_configure(
            self,
            dep: Dependency,
            extra_args: List[str] = [],
            configure_cmd: List[str] = ['./configure'],
            install: List[str] = ['install'],
            run_autogen: bool = False,
            autoconf: bool = False,
            src_subdir_name: Optional[str] = None,
            post_configure_action: Optional[Callable] = None) -> None:
        self.check_current_dir()
        log_prefix = self.log_prefix(dep)
        dir_for_build = os.getcwd()
        if src_subdir_name:
            dir_for_build = os.path.join(dir_for_build, src_subdir_name)

        with PushDir(dir_for_build):
            log("Building in %s using the configure tool", dir_for_build)
            try:
                if run_autogen:
                    self.log_output(log_prefix, ['./autogen.sh'])
                if autoconf:
                    self.log_output(log_prefix, ['autoreconf', '-i'])

                configure_args = (
                    configure_cmd.copy() + ['--prefix={}'.format(self.prefix)] + extra_args
                )
                configure_args = get_arch_switch_cmd_prefix() + configure_args
                self.log_output(
                    log_prefix,
                    configure_args,
                    disallowed_pattern=DISALLOWED_CONFIGURE_OUTPUT_RE)
            except Exception as ex:
                log(f"The configure step failed. Looking for relevant files in {dir_for_build} "
                    f"to show.")
                num_files_shown = 0
                for root, dirs, files in os.walk('.'):
                    for file_name in files:
                        if file_name == 'config.log':
                            file_path = os.path.abspath(os.path.join(root, file_name))
                            log(
                                f"Contents of {file_path}:\n"
                                f"\n"
                                f"{read_file(file_path)}\n"
                                f"\n"
                                f"(End of {file_path}).\n"
                                f"\n"
                            )
                            num_files_shown += 1
                log(f"Logged contents of {num_files_shown} relevant files in {dir_for_build}.")
                raise

            if post_configure_action:
                post_configure_action()

            self.log_output(log_prefix, ['make', '-j{}'.format(get_make_parallelism())])
            if install:
                self.log_output(log_prefix, ['make'] + install)

            self.validate_build_output()

    def log_output(
            self,
            prefix: str,
            args: List[Any],
            disallowed_pattern: Optional[Pattern] = None) -> None:
        log_output_internal(
            prefix=prefix,
            args=args,
            disallowed_pattern=disallowed_pattern,
            color=not self.args.concise_output,
            hide_log_on_success=self.args.concise_output)

    def build_with_cmake(
            self,
            dep: Dependency,
            extra_args: List[str] = [],
            use_ninja_if_available: bool = True,
            src_subdir_name: Optional[str] = None,
            extra_build_tool_args: List[str] = [],
            should_install: bool = True,
            install_targets: List[str] = ['install'],
            shared_and_static: bool = False) -> None:
        self.check_current_dir()
        build_tool = 'make'
        if use_ninja_if_available:
            ninja_available = is_ninja_available()
            log('Ninja is %s', 'available' if ninja_available else 'unavailable')
            if ninja_available:
                build_tool = 'ninja'

        log("Building dependency %s using CMake. Build tool: %s", dep, build_tool)
        log_prefix = self.log_prefix(dep)

        remove_path('CMakeCache.txt')
        remove_path('CMakeFiles')

        src_path = self.fs_layout.get_source_path(dep)
        if src_subdir_name is not None:
            src_path = os.path.join(src_path, src_subdir_name)

        args = ['cmake', src_path]
        if build_tool == 'ninja':
            args += ['-G', 'Ninja']
        args += self.get_common_cmake_flag_args(dep)
        if extra_args is not None:
            args += extra_args
        args += dep.get_additional_cmake_args(self)

        if shared_and_static and any(arg.startswith('-DBUILD_SHARED_LIBS=') for arg in args):
            raise ValueError(
                "shared_and_static=True is specified but CMake arguments already mention "
                "-DBUILD_SHARED_LIBS: %s" % args)

        if '-DBUILD_SHARED_LIBS=OFF' not in args and not shared_and_static:
            # TODO: a better approach for setting CMake arguments from multiple places.
            args.append('-DBUILD_SHARED_LIBS=ON')

        def do_build_with_cmake(additional_cmake_args: List[str] = []) -> None:
            final_cmake_args = args + additional_cmake_args
            log("CMake command line (one argument per line):\n%s" %
                format_cmake_args_for_log(final_cmake_args))
            cmake_configure_script_path = os.path.abspath('yb_build_with_cmake.sh')

            build_tool_cmd = [
                build_tool, '-j{}'.format(get_make_parallelism())
            ] + extra_build_tool_args

            log("Writing the command line for the CMake-based build to %s",
                os.path.abspath(cmake_configure_script_path))
            with open(cmake_configure_script_path, 'w') as cmake_configure_script_file:
                cmake_configure_script_file.write('\n'.join([
                    '#!/usr/bin/env bash',
                    'set -euxo pipefail',
                    'cd "$( dirname "$0" )"',
                    '. "./%s"' % DEPENDENCY_ENV_FILE_NAME,
                    shlex_join(final_cmake_args,
                               one_arg_per_line=True),
                    shlex_join(build_tool_cmd)
                ]) + '\n')
            os.chmod(cmake_configure_script_path,
                     stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP |
                     stat.S_IROTH)

            self.log_output(log_prefix, final_cmake_args)

            if build_tool == 'ninja':
                dep.postprocess_ninja_build_file(self, 'build.ninja')

            self.log_output(log_prefix, build_tool_cmd)

            if should_install:
                self.log_output(log_prefix, [build_tool] + install_targets)

            with open('compile_commands.json') as compile_commands_file:
                compile_commands = json.load(compile_commands_file)

            for command_item in compile_commands:
                command_args = command_item['command'].split()
                if self.build_type == BUILD_TYPE_ASAN:
                    assert_list_contains(command_args, '-fsanitize=address')
                    assert_list_contains(command_args, '-fsanitize=undefined')
                if self.build_type == BUILD_TYPE_TSAN:
                    assert_list_contains(command_args, '-fsanitize=thread')

        if shared_and_static:
            for build_shared_libs_value, subdir_name in (
                ('ON', 'shared'),
                ('OFF', 'static')
            ):
                build_dir = os.path.join(os.getcwd(), subdir_name)
                mkdir_if_missing(build_dir)
                build_shared_libs_cmake_arg = '-DBUILD_SHARED_LIBS=%s' % build_shared_libs_value
                log("Building dependency '%s' for build type '%s' with option: %s",
                    dep.name, self.build_type, build_shared_libs_cmake_arg)
                with PushDir(build_dir):
                    do_build_with_cmake([build_shared_libs_cmake_arg])
                    self.validate_build_output()
        else:
            do_build_with_cmake()
            self.validate_build_output()

    def build_with_bazel(
            self,
            dep: Dependency,
            verbose_output: bool = True,
            should_clean: bool = True,
            targets: List[str] = []) -> None:
        log_prefix = self.log_prefix(dep)
        if should_clean:
            self.log_output(log_prefix, ['bazel', 'clean', '--expunge'])

        # Need to remove the space after isystem so replacing the space separators with colons
        # works properly.
        bazel_cxxopts = os.environ["CXXFLAGS"].replace("isystem ", "isystem").replace(" ", ":")
        # Add stdlib=libc++ to avoid linking with libstdc++.
        bazel_linkopts = os.environ["LDFLAGS"].replace(" ", ":")

        # Build without curses for more readable build output.
        build_command = ["bazel", "build", "--curses=no"]
        if verbose_output:
            build_command.append("--subcommands")
        build_command += ["--action_env", f"BAZEL_CXXOPTS={bazel_cxxopts}"]
        build_command += ["--action_env", f"BAZEL_LINKOPTS={bazel_linkopts}"]

        # Need to explicitly pass environment variables which we want to be available.
        env_vars_to_copy = ["PATH", "CC", "CXX", "YB_THIRDPARTY_REAL_C_COMPILER",
                            "YB_THIRDPARTY_REAL_CXX_COMPILER", "YB_THIRDPARTY_USE_CCACHE"]
        for env_var in env_vars_to_copy:
            if env_var not in os.environ:
                log(f"Environment variable {env_var} not found. Not passing it to Bazel.")
                continue
            build_command += ["--action_env", f"{env_var}={os.environ[env_var]}"]

        for target in targets:
            self.log_output(log_prefix, build_command + [target])

    def install_bazel_build_output(
            self,
            dep: Dependency,
            src_file: str,
            dest_file: str,
            src_folder: str,
            is_shared: bool) -> None:
        log_prefix = self.log_prefix(dep)
        src_path = f'bazel-bin/{src_folder}/{src_file}'
        dest_path = os.path.join(self.prefix_lib, dest_file)

        # Fix permissions on libraries. Bazel builds write-protected files by default, which
        # prevents overwriting when building thirdparty multiple times.
        self.log_output(log_prefix, ['chmod', '755' if is_shared else '644', src_path])
        self.log_output(log_prefix, ['cp', src_path, dest_path])

    def validate_build_output(self) -> None:
        if is_macos():
            target_arch = get_target_arch()
            disallowed_suffix = ' ' + get_other_macos_arch(target_arch)
            log("Verifying achitecture of object files and libraries in %s (should be %s)",
                os.getcwd(), target_arch)
            object_files = subprocess.check_output(
                    ['find', os.getcwd(), '-name', '*.o', '-or', '-name', '*.dylib']
                ).strip().decode('utf-8').split('\n')
            for object_file_path in object_files:
                file_type = subprocess.check_output(['file', object_file_path]).strip().decode(
                        'utf-8')
                if file_type.endswith(disallowed_suffix):
                    raise ValueError(
                        "Incorrect object file architecture generated for %s (%s expected): %s" % (
                            object_file_path, target_arch, file_type))

    def check_spurious_a_out_file(self) -> None:
        """"
        Sometimes an a.out file gets generated in the top-level directory. This is an attempt to
        catch it and figure out how it is being generated.
        """
        spurious_a_out_path = os.path.join(YB_THIRDPARTY_DIR, 'a.out')
        if os.path.exists(spurious_a_out_path):
            log(f'The spurious a.out file got generated in {YB_THIRDPARTY_DIR}. Deleting it.'
                'In the future, we will track down where it is coming from.')
            os.remove(spurious_a_out_path)

    def build_one_build_type(self, build_type: str) -> None:
        if (build_type != BUILD_TYPE_COMMON and
                self.args.build_type is not None and
                build_type != self.args.build_type):
            log("Skipping build type %s because build type %s is specified in the arguments",
                build_type, self.args.build_type)
            return

        self.set_build_type(build_type)
        build_group = (
            BUILD_GROUP_COMMON if build_type == BUILD_TYPE_COMMON else BUILD_GROUP_INSTRUMENTED
        )

        for dep in self.selected_dependencies:
            if build_group == dep.build_group:
                self.perform_pre_build_steps(dep)
                should_build = dep.should_build(self)
                should_rebuild = self.should_rebuild_dependency(dep)
                if should_build and should_rebuild:
                    self.build_dependency(dep, only_process_flags=False)
                    self.check_spurious_a_out_file()
                else:
                    self.build_dependency(dep, only_process_flags=True)
                    log(f"Skipped dependency {dep.name}: "
                        f"should_build={should_build}, "
                        f"should_rebuild={should_rebuild}.")

    def get_install_prefix(self) -> str:
        return os.path.join(self.fs_layout.tp_installed_dir, self.build_type)

    def set_build_type(self, build_type: str) -> None:
        self.build_type = build_type
        self.prefix = self.get_install_prefix()
        self.prefix_bin = os.path.join(self.prefix, 'bin')
        self.prefix_lib = os.path.join(self.prefix, 'lib')
        self.prefix_include = os.path.join(self.prefix, 'include')

    def init_flags(self, dep: Dependency) -> None:
        """
        Initializes compiler and linker flags. No flag customizations should be transferred from one
        dependency to another.
        """
        self.init_compiler_independent_flags(dep)

        if not is_macos() and self.compiler_choice.using_clang():
            # Special setup for Clang on Linux.
            compiler_choice = self.compiler_choice
            llvm_major_version: Optional[int] = compiler_choice.get_llvm_major_version()
            if llvm_major_version is not None and llvm_major_version >= 10:
                self.init_linux_clang_flags(dep)
            else:
                raise ValueError(f"Unknown or unsupproted LLVM major version: {llvm_major_version}")

        if self.compiler_choice.using_gcc():
            self.cxx_flags.append('-fext-numeric-literals')

    def get_libcxx_dirs(self, libcxx_installed_suffix: str) -> Tuple[str, str]:
        libcxx_installed_path = os.path.join(
            self.fs_layout.tp_installed_dir, libcxx_installed_suffix, 'libcxx')
        libcxx_installed_include = os.path.join(libcxx_installed_path, 'include', 'c++', 'v1')
        libcxx_installed_lib = os.path.join(libcxx_installed_path, 'lib')
        return libcxx_installed_include, libcxx_installed_lib

    def init_linux_clang_flags(self, dep: Dependency) -> None:
        """
        Flags for Clang. We are using LLVM-supplied libunwind, and in most cases, compiler-rt in
        this configuration.
        """
        llvm_major_version = self.compiler_choice.get_llvm_major_version()
        assert llvm_major_version is not None

        if not using_linuxbrew():
            # We don't build compiler-rt for Linuxbrew yet.
            # TODO: we can build compiler-rt here the same way we build other LLVM components,
            # such as libunwind, libc++abi, and libc++.
            self.ld_flags.append('-rtlib=compiler-rt')

        self.ld_flags.append('-fuse-ld=lld')
        if self.lto_type is not None:
            self.compiler_flags.append('-flto=%s' % self.lto_type)

        clang_linuxbrew_isystem_flags = []

        if using_linuxbrew():
            linuxbrew_dir = get_linuxbrew_dir()
            assert linuxbrew_dir is not None
            self.ld_flags.append(
                '-Wl,--dynamic-linker=%s' % os.path.join(linuxbrew_dir, 'lib', 'ld.so'))
            self.compiler_flags.append('-nostdinc')
            self.compiler_flags.append('--gcc-toolchain={}'.format(linuxbrew_dir))

            assert self.compiler_choice.cc is not None
            clang_include_dir = get_clang_include_dir(self.compiler_choice.cc)

            clang_linuxbrew_isystem_flags = [
                '-isystem', clang_include_dir,

                # This is the include directory of the Linuxbrew GCC 5.5 / glibc 2.23 bundle.
                '-isystem', os.path.join(linuxbrew_dir, 'include')
            ]

        if self.build_type == BUILD_TYPE_COMMON:
            self.preprocessor_flags.extend(clang_linuxbrew_isystem_flags)
            return

        # TODO mbautin: refactor to polymorphism
        is_libcxxabi = dep.name.endswith('_libcxxabi')
        is_libcxx = dep.name.endswith('_libcxx')

        is_libcxx_with_abi = dep.name.endswith('_libcxx_with_abi')

        log("Dependency name: %s, is_libcxxabi: %s, is_libcxx: %s",
            dep.name, is_libcxxabi, is_libcxx)

        if self.build_type == BUILD_TYPE_ASAN:
            if is_libcxxabi or is_libcxx_with_abi:
                # To avoid an infinite loop in UBSAN.
                # https://monorail-prod.appspot.com/p/chromium/issues/detail?id=609786
                # This comment:
                # https://gist.githubusercontent.com/mbautin/ad9ea4715669da3b3a5fb9495659c4a9/raw
                self.compiler_flags.append('-fno-sanitize=vptr')

                # Unfortunately, for the combined libc++ and libc++abi build in Clang 13 or later,
                # we also disable this check in libc++, where in theory it could have been
                # enabled.

                # The description of this check from
                # https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html:
                #
                # -fsanitize=vptr: Use of an object whose vptr indicates that it is of the wrong
                # dynamic type, or that its lifetime has not begun or has ended. Incompatible with
                # -fno-rtti. Link must be performed by clang++, not clang, to make sure C++-specific
                # parts of the runtime library and C++ standard libraries are present.

            assert self.compiler_choice.cc is not None
            ubsan_lib_candidates = []
            ubsan_lib_found = False
            for ubsan_lib_arch_suffix in ['', f'-{platform.processor()}']:
                ubsan_lib_name = f'clang_rt.ubsan_minimal{ubsan_lib_arch_suffix}'
                ubsan_lib_file_name = f'lib{ubsan_lib_name}.so'
                compiler_rt_lib_dir_as_list = get_clang_library_dir(
                    self.compiler_choice.get_c_compiler(),
                    look_for_file=ubsan_lib_file_name)
                if not compiler_rt_lib_dir_as_list:
                    continue
                assert len(compiler_rt_lib_dir_as_list) == 1
                compiler_rt_lib_dir = compiler_rt_lib_dir_as_list[0]
                self.add_lib_dir_and_rpath(compiler_rt_lib_dir)

                ubsan_lib_so_path = os.path.join(compiler_rt_lib_dir, ubsan_lib_file_name)
                ubsan_lib_candidates.append(ubsan_lib_so_path)
                if os.path.exists(ubsan_lib_so_path):
                    self.ld_flags.append(f'-l{ubsan_lib_name}')
                    ubsan_lib_found = True
                    break
            if not ubsan_lib_found:
                raise IOError(
                    f"UBSAN library not found at any of the paths: {ubsan_lib_candidates}")
            llvm_major_version = self.compiler_choice.get_llvm_major_version()
            assert llvm_major_version is not None
            if (llvm_major_version >= 14 and
                    dep.build_group != BUILD_GROUP_COMMON and
                    dep.name != 'crcutil'):
                self.compiler_flags += ['-mllvm', '-asan-use-private-alias=1']

        if self.build_type == BUILD_TYPE_TSAN and llvm_major_version >= 13:
            self.executable_only_ld_flags.extend(['-fsanitize=thread'])

        self.ld_flags += ['-lunwind']

        libcxx_installed_include, libcxx_installed_lib = self.get_libcxx_dirs(self.build_type)
        log("libc++ include directory: %s", libcxx_installed_include)
        log("libc++ library directory: %s", libcxx_installed_lib)

        if not is_libcxx and not is_libcxxabi and not is_libcxx_with_abi:
            log("Adding special compiler/linker flags for Clang 10+ for dependencies other than "
                "libc++")
            self.ld_flags += ['-stdlib=libc++', '-lc++', '-lc++abi']
            # TODO(asrivastava): We might not need libc++ in cxxflags but removing it causes certain
            # builds to fail.
            self.cxx_flags += ['-stdlib=libc++', '-nostdinc++']
            self.preprocessor_flags.extend(['-isystem', libcxx_installed_include])
            self.prepend_lib_dir_and_rpath(libcxx_installed_lib)

        if is_libcxx:
            log("Adding special compiler/linker flags for Clang for libc++")
            # This is needed for libc++ to find libc++abi headers.
            assert_dir_exists(libcxx_installed_include)
            self.preprocessor_flags.append('-I%s' % libcxx_installed_include)
            # libc++ build needs to be able to find libc++abi library installed here.
            self.ld_flags.append('-L%s' % libcxx_installed_lib)

        if is_libcxx or is_libcxxabi or is_libcxx_with_abi:
            log("Adding special linker flags for Clang for libc++ or libc++abi")
            # libc++abi needs to be able to find libcxx at runtime, even though it can't always find
            # it at build time because libc++abi is built first.
            self.add_rpath(libcxx_installed_lib)

        self.preprocessor_flags.extend(clang_linuxbrew_isystem_flags)

        no_unused_arg = '-Wno-error=unused-command-line-argument'
        self.compiler_flags.append(no_unused_arg)
        self.ld_flags.append(no_unused_arg)

        log("Flags after the end of setup for Clang:")
        log("compiler_flags     : %s", self.compiler_flags)
        log("cxx_flags          : %s", self.cxx_flags)
        log("c_flags            : %s", self.c_flags)
        log("ld_flags           : %s", self.ld_flags)
        log("preprocessor_flags : %s", self.preprocessor_flags)

    def get_effective_compiler_flags(self, dep: Dependency) -> List[str]:
        return self.compiler_flags + dep.get_additional_compiler_flags(self)

    def get_effective_cxx_flags(self, dep: Dependency) -> List[str]:
        # The C++ standard must match CMAKE_CXX_STANDARD in the top-level CMakeLists.txt file in
        # the YugabyteDB source tree.
        return (self.cxx_flags +
                self.get_effective_compiler_flags(dep) +
                dep.get_additional_cxx_flags(self) +
                ['-std=c++{}'.format(dep.get_cxx_version(self))])

    def get_effective_c_flags(self, dep: Dependency) -> List[str]:
        return (self.c_flags +
                self.get_effective_compiler_flags(dep) +
                dep.get_additional_c_flags(self))

    def get_effective_ld_flags(self, dep: Dependency) -> List[str]:
        return (dep.get_additional_leading_ld_flags(self) +
                self.ld_flags +
                dep.get_additional_ld_flags(self))

    def get_effective_assembler_flags(self, dep: Dependency) -> List[str]:
        return self.assembler_flags + dep.get_additional_assembler_flags(self)

    def get_effective_executable_ld_flags(self, dep: Dependency) -> List[str]:
        return self.ld_flags + self.executable_only_ld_flags + dep.get_additional_ld_flags(self)

    def get_effective_preprocessor_flags(self, dep: Dependency) -> List[str]:
        return list(self.preprocessor_flags)

    def get_common_cmake_flag_args(self, dep: Dependency) -> List[str]:
        assert not dep.use_cppflags_env_var(), \
            f'Dependency {dep.name} is being built with CMake but its use_cppflags_env_var ' \
            'function returns True. CPPFLAGS only applies to configure-based builds.'

        preprocessor_flags = self.get_effective_preprocessor_flags(dep)
        c_flags_str = ' '.join(preprocessor_flags + self.get_effective_c_flags(dep))
        cxx_flags_str = ' '.join(preprocessor_flags + self.get_effective_cxx_flags(dep))

        ld_flags_str = ' '.join(self.get_effective_ld_flags(dep))
        exe_ld_flags_str = ' '.join(self.get_effective_executable_ld_flags(dep))
        return [
            '-DCMAKE_C_FLAGS={}'.format(c_flags_str),
            '-DCMAKE_CXX_FLAGS={}'.format(cxx_flags_str),
            '-DCMAKE_SHARED_LINKER_FLAGS={}'.format(ld_flags_str),
            '-DCMAKE_EXE_LINKER_FLAGS={}'.format(exe_ld_flags_str),
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
            '-DCMAKE_INSTALL_PREFIX={}'.format(dep.get_install_prefix(self)),
            '-DCMAKE_POSITION_INDEPENDENT_CODE=ON'
        ]

    def perform_pre_build_steps(self, dep: Dependency) -> None:
        log("")
        colored_log(YELLOW_COLOR, SEPARATOR)
        colored_log(YELLOW_COLOR, "Building %s (%s)", dep.name, self.build_type)
        colored_log(YELLOW_COLOR, SEPARATOR)

        log("Downloading %s", dep)
        self.download_manager.download_dependency(
            dep=dep,
            src_path=self.fs_layout.get_source_path(dep),
            archive_path=self.fs_layout.get_archive_path(dep))

        self.fossa_deps.append({
            "name": dep.name,
            "version": dep.version,
            "url": dep.download_url
        })

    def build_dependency(self, dep: Dependency, only_process_flags: bool = False) -> None:
        """
        Build the given dependency.

        :param only_process_flags: if this is True, we will only set up the compiler and linker
            flags and apply all the side effects of that process, such as collecting the set of
            allowed library paths referred by the final artifacts. If False, we will actually do
            the build.
        """

        self.compiler_choice.set_compiler(
            use_compiler_wrapper=self.args.use_compiler_wrapper or dep.need_compiler_wrapper(self))
        if self.args.download_extract_only:
            log("Skipping build of dependency %s, build type %s, --download-extract-only is "
                "specified.", dep.name, self.build_type)
            return

        self.init_flags(dep)

        # This is needed at least for glog to be able to find gflags.
        self.add_rpath(os.path.join(self.fs_layout.tp_installed_dir, self.build_type, 'lib'))

        if self.build_type != BUILD_TYPE_COMMON:
            # Needed to find libunwind for Clang 10 when using compiler-rt.
            self.add_rpath(os.path.join(self.fs_layout.tp_installed_dir, BUILD_TYPE_COMMON, 'lib'))

        if only_process_flags:
            log("Skipping the build of dependecy %s", dep.name)
            return

        env_vars: Dict[str, Optional[str]] = {
            "CPPFLAGS": " ".join(self.preprocessor_flags)
        }

        use_cppflags_env_var = dep.use_cppflags_env_var()
        preprocessor_flags = self.get_effective_preprocessor_flags(dep)

        cppflags_list: List[str] = []
        if use_cppflags_env_var:
            # Preprocessor flags are specified as CPPFLAGS.
            preprocessor_flags_in_compiler_flags = []
            cppflags_list = preprocessor_flags
        else:
            # Preprocessor flags are specified in CXXFLAGS and CFLAGS directly.
            preprocessor_flags_in_compiler_flags = preprocessor_flags
            cppflags_list = []

        log_and_set_env_var_to_list(env_vars, 'CPPFLAGS', cppflags_list)

        log_and_set_env_var_to_list(
            env_vars,
            'CXXFLAGS',
            preprocessor_flags_in_compiler_flags + self.get_effective_cxx_flags(dep))
        log_and_set_env_var_to_list(
            env_vars,
            'CFLAGS',
            preprocessor_flags_in_compiler_flags + self.get_effective_c_flags(dep))
        log_and_set_env_var_to_list(env_vars, 'LDFLAGS', self.get_effective_ld_flags(dep))
        log_and_set_env_var_to_list(
            env_vars, 'ASFLAGS', self.get_effective_assembler_flags(dep))
        log_and_set_env_var_to_list(env_vars, 'LIBS', self.libs)

        compiler_wrapper_extra_ld_flags = dep.get_compiler_wrapper_ld_flags_to_append(self)
        if compiler_wrapper_extra_ld_flags:
            if not self.compiler_choice.use_compiler_wrapper:
                raise RuntimeError(
                    "Need to add extra linker arguments in the compiler wrapper, but compiler "
                    "wrapper is not being used: %s" % compiler_wrapper_extra_ld_flags)
            log_and_set_env_var_to_list(
                env_vars, COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_APPEND,
                compiler_wrapper_extra_ld_flags)

        compiler_wrapper_ld_flags_to_remove: Set[str] = dep.get_compiler_wrapper_ld_flags_to_remove(
            self)
        if compiler_wrapper_ld_flags_to_remove:
            if not self.compiler_choice.use_compiler_wrapper:
                raise RuntimeError(
                    "Need to remove some linker arguments in the compiler wrapper, but compiler "
                    "wrapper is not being used: %s" % sorted(compiler_wrapper_ld_flags_to_remove))
            log_and_set_env_var_to_list(
                env_vars, COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_REMOVE,
                sorted(compiler_wrapper_ld_flags_to_remove))

        for k, v in env_vars.items():
            log("Setting environment variable %s to: %s" % (k, v))

        if self.build_type == BUILD_TYPE_ASAN:
            # To avoid errors similar to:
            # https://gist.githubusercontent.com/mbautin/4b8eec566f54bcc35706dcd97cab1a95/raw
            #
            # This could also be fixed to some extent by the compiler flags
            # -mllvm -asan-use-private-alias=1
            # but applying that flag to all builds is complicated in practice and is probably
            # best done using a compiler wrapper script, which would slow things down.
            #
            # Also do not detect memory leaks during the build process. E.g. configure scripts might
            # create some programs that have memory leaks and the configure process would fail.
            env_vars["ASAN_OPTIONS"] = ':'.join(["detect_odr_violation=0", "detect_leaks=0"])

        with PushDir(self.create_build_dir_and_prepare(dep)):
            with EnvVarContext(**env_vars):
                write_env_vars(DEPENDENCY_ENV_FILE_NAME)
                log("PATH=%s" % os.getenv('PATH'))
                dep.build(self)
        self.save_build_stamp_for_dependency(dep)
        log("")
        log("Finished building %s (%s)", dep.name, self.build_type)
        log("")

    # Determines if we should rebuild a component with the given name based on the existing "stamp"
    # file and the current value of the "stamp" (based on Git SHA1 and local changes) for the
    # component. The result is returned in should_rebuild_component_rv variable, which should have
    # been made local by the caller.
    def should_rebuild_dependency(self, dep: Dependency) -> bool:
        stamp_path = self.fs_layout.get_build_stamp_path_for_dependency(dep, self.build_type)
        old_build_stamp = None
        if os.path.exists(stamp_path):
            with open(stamp_path, 'rt') as inp:
                old_build_stamp = inp.read()

        new_build_stamp = self.get_build_stamp_for_dependency(dep)

        dep_name_and_build_type_str = "%s (%s)" % (dep.name, self.build_type)

        if dep.dir_name is not None:
            src_dir = self.fs_layout.get_source_path(dep)
            if not os.path.exists(src_dir):
                log("Have to rebuild %s: source dir %s does not exist",
                    dep_name_and_build_type_str, src_dir)
                return True

        build_dir = self.fs_layout.get_build_dir_for_dependency(dep, self.build_type)
        if not os.path.exists(build_dir):
            log("Have to rebuild %s: build dir %s does not exist",
                dep_name_and_build_type_str, build_dir)
            return True

        if old_build_stamp == new_build_stamp:
            if self.args.force:
                log("No changes detected for %s, rebuilding anyway (--force specified).",
                    dep_name_and_build_type_str)
            else:
                log("Not rebuilding %s -- nothing changed.", dep_name_and_build_type_str)
                return False

        log("Have to rebuild %s (%s):", dep.name, self.build_type)
        log("Old build stamp for %s (from %s):\n%s",
            dep.name, stamp_path, indent_lines(old_build_stamp))
        log("New build stamp for %s:\n%s",
            dep.name, indent_lines(new_build_stamp))
        return True

    # Come up with a string that allows us to tell when to rebuild a particular third-party
    # dependency. The result is returned in the get_build_stamp_for_component_rv variable, which
    # should have been made local by the caller.
    def get_build_stamp_for_dependency(self, dep: Dependency) -> str:
        module_name = dep.__class__.__module__
        assert isinstance(module_name, str), "Dependency's module is not a string: %s" % module_name
        assert module_name.startswith('build_definitions.'), "Invalid module name: %s" % module_name
        module_name_components = module_name.split('.')
        assert len(module_name_components) == 2, (
                "Expected two components: %s" % module_name_components)
        module_name_final = module_name_components[-1]
        input_files_for_stamp = [
            'python/yugabyte_db_thirdparty/yb_build_thirdparty_main.py',
            'build_thirdparty.sh',
            os.path.join('python', 'build_definitions', '%s.py' % module_name_final)
        ]

        for path in input_files_for_stamp:
            abs_path = os.path.join(YB_THIRDPARTY_DIR, path)
            if not os.path.exists(abs_path):
                fatal("File '%s' does not exist -- expecting it to exist when creating a 'stamp' "
                      "for the build configuration of '%s'.", abs_path, dep.name)

        with PushDir(YB_THIRDPARTY_DIR):
            git_commit_sha1 = subprocess.check_output(
                ['git', 'log', '--pretty=%H', '-n', '1'] + input_files_for_stamp
            ).strip().decode('utf-8')
            build_stamp = 'git_commit_sha1={}\n'.format(git_commit_sha1)
            for git_extra_arg in (None, '--cached'):
                git_extra_args = [git_extra_arg] if git_extra_arg else []
                git_diff = subprocess.check_output(
                    ['git', 'diff'] + git_extra_args + input_files_for_stamp)
                git_diff_sha256 = hashlib.sha256(git_diff).hexdigest()
                build_stamp += 'git_diff_sha256{}={}\n'.format(
                    '_'.join(git_extra_args).replace('--', '_'),
                    git_diff_sha256)
            return build_stamp

    def save_build_stamp_for_dependency(self, dep: Dependency) -> None:
        stamp = self.get_build_stamp_for_dependency(dep)
        stamp_path = self.fs_layout.get_build_stamp_path_for_dependency(dep, self.build_type)

        log("Saving new build stamp to '%s':\n%s", stamp_path, indent_lines(stamp))
        with open(stamp_path, "wt") as out:
            out.write(stamp)

    def create_build_dir_and_prepare(self, dep: Dependency) -> str:
        src_dir = self.fs_layout.get_source_path(dep)
        if not os.path.isdir(src_dir):
            fatal("Directory '{}' does not exist".format(src_dir))

        build_dir = self.fs_layout.get_build_dir_for_dependency(dep, self.build_type)

        if self.args.delete_build_dir:
            log("Deleting directory %s (--delete-build-dir specified)", build_dir)
            subprocess.check_call(['rm', '-rf', build_dir])
        mkdir_if_missing(build_dir)

        if dep.copy_sources:
            if dep.shared_and_static:
                target_dirs = [
                    os.path.join(build_dir, subdir_name)
                    for subdir_name in ['shared', 'static']
                ]
            else:
                target_dirs = [build_dir]

            for target_dir in target_dirs:
                log("Bootstrapping %s from %s using rsync", target_dir, src_dir)
                bootstrap_start_sec = time.time()
                subprocess.check_call(['rsync', '-a', src_dir + '/', target_dir])
                bootstrap_elapsed_sec = time.time() - bootstrap_start_sec
                log("Bootstrapping %s took %.3f sec", target_dir, bootstrap_elapsed_sec)

        return build_dir

    def is_release_build(self) -> bool:
        """
        Distinguishes between build types that are potentially used in production releases from
        build types that are only used in testing (e.g. ASAN+UBSAN, TSAN).
        """
        return self.build_type in [BUILD_TYPE_COMMON, BUILD_TYPE_UNINSTRUMENTED]

    def cmake_build_type_for_test_only_dependencies(self) -> str:
        return 'Release' if self.is_release_build() else 'Debug'

    def check_cxx_compiler_flag(self, flag: str) -> bool:
        compiler_path = self.compiler_choice.get_cxx_compiler()
        log(f"Checking if the compiler {compiler_path} accepts the flag {flag}")
        process = subprocess.Popen(
            [compiler_path, '-x', 'c++', flag, '-'],
            stdin=subprocess.PIPE)
        assert process.stdin is not None
        process.stdin.write("int main() { return 0; }".encode('utf-8'))
        process.stdin.close()
        return process.wait() == 0

    def add_checked_flag(self, flags: List[str], flag: str) -> None:
        if self.check_cxx_compiler_flag(flag):
            flags.append(flag)

    def get_openssl_dir(self) -> str:
        return os.path.join(self.fs_layout.tp_installed_common_dir)

    def get_openssl_related_cmake_args(self) -> List[str]:
        """
        Returns a list of CMake arguments to use to pick up the version of OpenSSL that we should be
        using. Returns an empty list if the default OpenSSL installation should be used.
        """
        openssl_dir = self.get_openssl_dir()
        openssl_options = ['-DOPENSSL_ROOT_DIR=' + openssl_dir]
        openssl_crypto_library = os.path.join(
            openssl_dir, 'lib', 'libcrypto.' + self.shared_lib_suffix)
        openssl_ssl_library = os.path.join(openssl_dir, 'lib', 'libssl.' + self.shared_lib_suffix)
        openssl_options += [
            '-DOPENSSL_CRYPTO_LIBRARY=' + openssl_crypto_library,
            '-DOPENSSL_SSL_LIBRARY=' + openssl_ssl_library,
            '-DOPENSSL_LIBRARIES=%s;%s' % (openssl_crypto_library, openssl_ssl_library)
        ]
        return openssl_options
