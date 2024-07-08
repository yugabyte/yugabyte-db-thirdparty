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

"""
Checking that the executables and shared libraries we have built don't depend on any unexpected
shared libraries installed on this system.
"""

import os
import sys
import re
import subprocess
import platform
import logging

from sys_detection import is_macos, is_linux

from typing import List, Any, Set, Optional, Pattern, Type

from yugabyte_db_thirdparty.custom_logging import log, fatal, heading
from yugabyte_db_thirdparty.util import YB_THIRDPARTY_DIR, capture_all_output, shlex_join
from yugabyte_db_thirdparty.macos import get_min_supported_macos_version
from yugabyte_db_thirdparty.file_system_layout import FileSystemLayout
from yugabyte_db_thirdparty.compiler_choice import CompilerChoice
from yugabyte_db_thirdparty.ldd_util import run_ldd

from yugabyte_db_thirdparty import patchelf_util

from build_definitions import BuildType


IGNORED_EXTENSIONS = (
    '.a',
    '.la',
    '.pc',
    '.inc',
    '.h',
    '.hpp',
    '.cmake',
)

IGNORED_FILE_NAMES = set([
    'LICENSE',
    'krb5-send-pr',
    '.clang-format',
])

IGNORED_DIR_SUFFIXES = (
    '/include/c++/v1',
    '/include/c++/v1/experimental',
    '/include/c++/v1/ext',
)

ALLOWED_SYSTEM_LIBRARIES = (
    # These libraries are part of glibc.
    'libc',
    'libdl',
    'libm',
    'libpthread',
    'libresolv',
    'librt',
    'libutil',
    # When we use Linuxbrew, we can also see ld-linux-x86-64.so.2 in ldd output.
    'ld-linux',
)

SKIPPED_LDD_OUTPUT_PREFIXES = (
    'Unused ',
    'ldd: warning: ',
    'not a dynamic'
)

NEEDED_LIBS_TO_REMOVE = (
    'libatomic',
)

LIBCXX_NOT_FOUND = re.compile(r'^\tlibc[+][+][.]so[.][0-9]+ => not found')
SYSTEM_LIBRARY_RE = re.compile(
    r'^.* => /lib(?:64|/(?:x86_64|aarch64)-linux-gnu)/([^ /]+) .*$')


def compile_re_list(re_list: List[str]) -> Any:
    return re.compile("|".join(re_list))


def get_needed_libs(file_path: str) -> List[str]:
    if file_path.endswith(IGNORED_EXTENSIONS) or os.path.basename(file_path) in IGNORED_FILE_NAMES:
        return []
    return capture_all_output(
        [patchelf_util.get_patchelf_path(), '--print-needed', file_path],
        allowed_exit_codes={1},
        extra_msg_on_nonzero_exit_code="Warning: could not determine libraries directly "
                                       f"needed by {file_path}")


def is_text_based_so_file(so_path: str) -> bool:
    # libc++.so is a text file containing this:
    # INPUT(libc++.so.1 -lunwind -lc++abi)
    # We can't analyze this kind of a file with ldd so we skip it.
    with open(so_path, 'rb') as input_file:
        first_bytes = input_file.read(64)
        return first_bytes.startswith(b'INPUT')


class LibTestBase:
    """
    Verify correct library paths are used in installed dynamically-linked executables and
    libraries. Also verify certain properies of static libraries, e.g. minimum supported macOS
    version.
    """

    tp_installed_dir: str
    lib_re_list: List[str]
    tool: str

    # A compiled regex containing almost all of the allowed patterns (except for an an optional
    # additional pattern).
    allowed_patterns: Pattern

    # To make sure that we log each allowed pattern no more than once.
    logged_allowed_patterns: Set[str]

    extra_allowed_shared_lib_paths: Set[str]

    # We collect all files to check in this list.
    files_to_check: List[str]

    allowed_system_libraries: Set[str]
    needed_libs_to_remove: Set[str]

    fs_layout: FileSystemLayout

    def __init__(self, fs_layout: FileSystemLayout) -> None:
        self.lib_re_list = []
        self.logged_allowed_patterns = set()
        self.extra_allowed_shared_lib_paths = set()
        self.allowed_system_libraries = set(ALLOWED_SYSTEM_LIBRARIES)
        self.needed_libs_to_remove = set(NEEDED_LIBS_TO_REMOVE)
        self.fs_layout = fs_layout
        self.tp_installed_dir = fs_layout.tp_installed_dir

    def configure_for_compiler(self, compiler_choice: CompilerChoice) -> None:
        if compiler_choice.using_gcc():
            # The GCC toolchain links with the libstdc++ library in a system-wide location.
            self.allowed_system_libraries.add('libstdc++')

        if (compiler_choice.using_gcc() or
                compiler_choice.using_clang() and
                compiler_choice.is_llvm_major_version_at_least(13)):
            # For GCC and Clang 13+, there are some issues with removing the libgcc_s dependency
            # from libraries even if it is apparently not needed as shown by "ldd -u".
            self.allowed_system_libraries.add('libgcc_s')
        else:
            # For Clang 12, it looks like we can safely remove the libgcc_s dependency.
            self.needed_libs_to_remove.add('libgcc_s')

        if compiler_choice.using_gcc_major_version_at_least(11):
            # When building DiskANN with GCC 11+, we end up using the system OpenMP library called
            # libgomp.so.1.
            self.allowed_system_libraries.add('libgomp')

    def init_regex(self) -> None:
        self.allowed_patterns = compile_re_list(self.lib_re_list)

    def check_lib_deps(
            self,
            file_path: str,
            cmd_output: List[str],
            additional_allowed_pattern: Optional[Pattern] = None) -> bool:

        status = True
        for line in cmd_output:
            if (not self.allowed_patterns.match(line) and
                    not (additional_allowed_pattern is not None and
                         additional_allowed_pattern.match(line))):
                # Log the allowed patterns for easier debugging.
                for allowed_pattern in [self.allowed_patterns] + (
                    [additional_allowed_pattern] if additional_allowed_pattern else []
                ):
                    if allowed_pattern.pattern not in self.logged_allowed_patterns:
                        log("Allowed pattern: %s", allowed_pattern.pattern)
                        self.logged_allowed_patterns.add(allowed_pattern.pattern)

                if status:
                    log(file_path + ":")
                    status = False
                log("Bad path: %s", line)

        return status

    def check_libs_for_file(self, file_path: str) -> bool:
        """
        Checks if the given file's shared libraries resolve in a correct way. Overridden in
        OS-specific classes.
        """
        raise NotImplementedError()

    def should_check_file(self, file_path: str) -> bool:
        if (os.path.islink(file_path) or
                is_text_based_so_file(file_path) or
                file_path.endswith(IGNORED_EXTENSIONS) or
                os.path.basename(file_path) in IGNORED_FILE_NAMES):
            return False

        file_dir = os.path.dirname(file_path)
        return not any(file_dir.endswith(suffix) for suffix in IGNORED_DIR_SUFFIXES)

    def run(self) -> None:
        self.init_regex()
        heading("Scanning installed executables and libraries...")
        for allowed_shared_lib_path in sorted(self.extra_allowed_shared_lib_paths):
            log("Extra allowed shared lib path: %s", allowed_shared_lib_path)
        test_pass = True
        # Files to examine are much reduced if we look only at bin and lib directories.
        # A special case is the DiskANN dependency, which has its own subdirectory.
        dir_pattern = re.compile('^(lib|libcxx|[s]bin|diskann)$')
        installed_dirs_per_build_type = [
                os.path.join(self.tp_installed_dir, build_type.dir_name)
                for build_type in BuildType]

        self.files_to_check = []
        for installed_dir_for_one_build_type in installed_dirs_per_build_type:
            if not os.path.isdir(installed_dir_for_one_build_type):
                logging.info("Directory %s does not exist, skipping",
                             installed_dir_for_one_build_type)
                continue
            with os.scandir(installed_dir_for_one_build_type) as candidate_dirs:
                for candidate in candidate_dirs:
                    if dir_pattern.match(candidate.name):
                        examine_path = os.path.join(
                                installed_dir_for_one_build_type, candidate.name)
                        for dirpath, dir_names, files in os.walk(examine_path):
                            for file_name in files:
                                full_path = os.path.join(dirpath, file_name)
                                if not self.should_check_file(full_path):
                                    continue
                                self.files_to_check.append(full_path)

        self.before_checking_all_files()
        test_pass = self.check_all_files()

        if not test_pass:
            fatal(f"Found problematic library dependencies, using tool: {self.tool}")
        else:
            log("No problems found with library dependencies.")

    def before_checking_all_files(self) -> None:
        pass

    def check_all_files(self) -> bool:
        success = True
        for file_path in self.files_to_check:
            if not self.check_libs_for_file(file_path):
                # We are not returning here because we want to log all errors.
                success = False
        return success

    def add_allowed_shared_lib_paths(self, shared_lib_paths: Set[str]) -> None:
        self.extra_allowed_shared_lib_paths |= shared_lib_paths


class LibTestMac(LibTestBase):
    def __init__(self, fs_layout: FileSystemLayout) -> None:
        super().__init__(fs_layout=fs_layout)
        self.tool = "otool -L"
        self.lib_re_list = [
            "^\t/System/Library/",
            "^Archive ",
            "^/",
            "^\t@rpath",
            "^\t@loader_path",
            f"^\t{YB_THIRDPARTY_DIR}",
            # We don't allow to use libraries from /usr/local/... because Homebrew libraries are
            # installed there and we try to rely on as few of those as possible.
            "^\t/usr/lib/",
        ]

    def check_libs_for_file(self, file_path: str) -> bool:
        otool_output = subprocess.check_output(['otool', '-L', file_path]).decode('utf-8')
        if 'is not an object file' in otool_output:
            return True

        if not self.check_lib_deps(file_path, otool_output.splitlines()):
            return False

        min_supported_macos_version = get_min_supported_macos_version()

        # Additionally, check for the minimum macOS version encoded in the library file.
        otool_small_l_output = subprocess.check_output(['otool', '-l', file_path]).decode('utf-8')
        section = ""
        for line in otool_small_l_output.split('\n'):
            line = line.strip()
            if line.endswith(':'):
                section = line
            if line.startswith('minos '):
                items = line.split()
                min_macos_version = items[1]
                if min_macos_version != min_supported_macos_version:
                    log("File %s has wrong minimum supported macOS version: %s. Full line:\n%s\n"
                        "(output from 'otool -l'). Expected: %s, section: %s",
                        file_path, min_macos_version, line, min_supported_macos_version,
                        section)
                    return False

        return True


class LibTestLinux(LibTestBase):
    def __init__(self, fs_layout: FileSystemLayout) -> None:
        super().__init__(fs_layout=fs_layout)
        self.tool = "ldd"
        self.lib_re_list = [
            "^\tlinux-vdso",
            "^\t/lib64/",
            "^\t/lib/ld-linux-.*",
            "^\t/opt/yb-build/brew/linuxbrew",
            "^\tstatically linked",
            "^\tnot a dynamic executable",
            "ldd: warning: you do not have execution permission",
            "^.* => /lib64/",
            "^.* => /lib/",
            "^.* => /usr/lib/x86_64-linux-gnu/",
            "^.* => /opt/yb-build/brew/linuxbrew",
            f"^.* => {re.escape(YB_THIRDPARTY_DIR)}"
        ]

    def add_allowed_shared_lib_paths(self, shared_lib_paths: Set[str]) -> None:
        super().add_allowed_shared_lib_paths(shared_lib_paths)
        for shared_lib_path in sorted(shared_lib_paths):
            self.lib_re_list.append(f".* => {re.escape(shared_lib_path)}/")

    def before_checking_all_files(self) -> None:
        for file_path in self.files_to_check:
            self.fix_needed_libs_for_file(file_path)

    def fix_needed_libs_for_file(self, file_path: str) -> None:
        needed_libs: List[str] = get_needed_libs(file_path)

        if needed_libs:
            ldd_u_cmd = ['ldd', '-u', file_path]
            ldd_u_cmd_str = shlex_join(ldd_u_cmd)
            ldd_u_output_lines: List[str] = capture_all_output(ldd_u_cmd, allowed_exit_codes={1})
            removed_libs: List[str] = []
            for ldd_u_output_line in ldd_u_output_lines:
                ldd_u_output_line = ldd_u_output_line.strip()
                if ldd_u_output_line.startswith('Inconsistency'):
                    raise IOError(f'ldd -u failed on file {file_path}: {ldd_u_output_line}')
                if ldd_u_output_line.startswith(SKIPPED_LDD_OUTPUT_PREFIXES):
                    continue
                unused_lib_path = ldd_u_output_line

                if not os.path.exists(unused_lib_path):
                    raise IOError(
                        f"File does not exist: {unused_lib_path} "
                        f"(obtained as an output line from command: {ldd_u_cmd_str})")
                unused_lib_name = os.path.basename(unused_lib_path)
                if unused_lib_name.startswith('ld-linux-'):
                    continue
                if unused_lib_name not in needed_libs:
                    raise ValueError(
                        "Unused library %s does not appear in the list of needed libs: %s "
                        "(for file %s)" % (unused_lib_path, needed_libs, file_path))
                if any([unused_lib_name.startswith(lib_name + '.')
                        for lib_name in self.needed_libs_to_remove]):
                    subprocess.check_call([
                        patchelf_util.get_patchelf_path(),
                        '--remove-needed',
                        unused_lib_name,
                        file_path
                    ])
                    log("Removed unused needed lib %s from %s", unused_lib_name, file_path)
                    removed_libs.append(unused_lib_name)
            new_needed_libs = get_needed_libs(file_path)
            for removed_lib in removed_libs:
                if removed_lib in new_needed_libs:
                    raise ValueError(f"Failed to remove needed library {removed_lib} from "
                                     f"{file_path}. File's current needed libs: {new_needed_libs}")

    def is_allowed_system_lib(
            self, lib_name: str, additional_allowed_libraries: List[str] = []) -> bool:
        return any(lib_name.startswith(
            (allowed_lib_name + '.', allowed_lib_name + '-'))
            for allowed_lib_name in (
                list(self.allowed_system_libraries) + additional_allowed_libraries
            ))

    def check_libs_for_file(self, file_path: str) -> bool:
        assert os.path.isabs(file_path), "Expected absolute path, got: %s" % file_path
        file_basename = os.path.basename(file_path)
        rel_path_to_installed_dir = os.path.relpath(
            os.path.abspath(file_path), self.tp_installed_dir)
        is_sanitizer = rel_path_to_installed_dir.startswith(('asan/', 'tsan/'))

        additional_allowed_pattern = None
        if file_basename.startswith('libc++abi.so.'):
            # One exception: libc++abi.so is not able to find libc++ because it loads the ASAN
            # runtime library that is part of the LLVM distribution and does not have the correct
            # rpath set. This happens on CentOS with our custom build of LLVM. We might be able to
            # fix this by specifying rpath correctly when building LLVM, but as of 12/2020 we just
            # ignore this error here.
            #
            # $ ldd installed/asan/libcxx/lib/libc++abi.so.1.0
            #   linux-vdso.so.1 =>
            #   libclang_rt.asan-x86_64.so =>
            #     $LLVM_DIR/lib/clang/11.0.0/lib/linux/libclang_rt.asan-x86_64.so
            #   libclang_rt.ubsan_minimal-x86_64.so =>
            #     $LLVM_DIR/lib/clang/11.0.0/lib/linux/libclang_rt.ubsan_minimal-x86_64.so
            #   libunwind.so.1 => installed/common/lib/libunwind.so.1
            #   libdl.so.2 => /lib64/libdl.so.2
            #   libpthread.so.0 => /lib64/libpthread.so.0
            #   libm.so.6 => /lib64/libm.so.6
            #   libc.so.6 => /lib64/libc.so.6
            #   libc++.so.1 => not found  <-- THIS IS OK
            #   libgcc_s.so.1 => /lib64/libgcc_s.so.1
            #   librt.so.1 => /lib64/librt.so.1
            #   /lib64/ld-linux-x86-64.so.2
            #
            # Run
            #   LD_DEBUG=all ldd installed/asan/libcxx/lib/libc++abi.so.1.0
            # and notice the following line:
            #
            # file=libc++.so.1 [0];
            #   needed by $LLVM_DIR/lib/clang/11.0.0/lib/linux/libclang_rt.asan-x86_64.so
            #
            # Also running
            #   ldd $LLVM_DIR/lib/clang/11.0.0/lib/linux/libclang_rt.asan-x86_64.so
            #
            # reports "libc++.so.1 => not found".
            additional_allowed_pattern = LIBCXX_NOT_FOUND

        ldd_result = run_ldd(file_path)
        if ldd_result.not_a_dynamic_executable():
            return True

        success = True

        additional_allowed_libraries = []
        if is_sanitizer:
            # In ASAN builds, libc++ and libc++abi libraries end up depending on the system's
            # libgcc_s and that's OK because we are not trying to make those builds portable
            # across different Linux distributions.
            additional_allowed_libraries.append('libgcc_s')

        ldd_output_lines = ldd_result.output_lines
        for line in ldd_output_lines:
            match = SYSTEM_LIBRARY_RE.search(line.strip())
            if match:
                system_lib_name = match.group(1)
                if not self.is_allowed_system_lib(
                        system_lib_name,
                        additional_allowed_libraries=additional_allowed_libraries):
                    log("Disallowed system library: %s. Allowed: %s. File: %s",
                        system_lib_name, sorted(self.allowed_system_libraries), file_path)
                    success = False

        return self.check_lib_deps(
            file_path, ldd_output_lines, additional_allowed_pattern) and success


def get_lib_tester(fs_layout: FileSystemLayout) -> LibTestBase:
    lib_tester_class: Type[LibTestBase]
    if is_macos():
        lib_tester_class = LibTestMac
    elif is_linux():
        lib_tester_class = LibTestLinux
    else:
        fatal(f"Unsupported platform: {platform.system()}")
    return lib_tester_class(fs_layout=fs_layout)
