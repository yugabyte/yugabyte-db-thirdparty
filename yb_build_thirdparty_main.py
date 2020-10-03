#!/usr/bin/env python3

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


import argparse
import hashlib
import multiprocessing
import os
import platform
import random
import re
import subprocess
import sys
import time
from datetime import datetime

from typing import Set, List, Dict, Optional, Tuple, Union, cast

from yugabyte_db_thirdparty.shared_library_checking import get_lib_tester
from yugabyte_db_thirdparty.builder_interface import BuilderInterface
from overrides import overrides  # type: ignore
import build_definitions
from build_definitions import *  # noqa

import_submodules(build_definitions)

CHECKSUM_FILE_NAME = 'thirdparty_src_checksums.txt'
CLOUDFRONT_URL = 'http://d3dr9sfxru4sde.cloudfront.net/{}'
MAX_FETCH_ATTEMPTS = 10
INITIAL_DOWNLOAD_RETRY_SLEEP_TIME_SEC = 1.0
DOWNLOAD_RETRY_SLEEP_INCREASE_SEC = 0.5

PLACEHOLDER_RPATH = (
    "/tmp/making_sure_we_have_enough_room_to_set_rpath_later_{}_end_of_rpath".format('_' * 256))

PLACEHOLDER_RPATH_FOR_LOG = '/tmp/long_placeholder_rpath'


def hashsum_file(hash: Any, filename: str, block_size: int = 65536) -> str:
    # TODO: use a more precise argument type for hash.
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            hash.update(block)
    return hash.hexdigest()


def indent_lines(s: Optional[str], num_spaces: int = 4) -> Optional[str]:
    if s is None:
        return s
    return "\n".join([
        ' ' * num_spaces + line for line in s.split("\n")
    ])


def get_make_parallelism() -> int:
    return int(os.environ.get('YB_MAKE_PARALLELISM', multiprocessing.cpu_count()))


def where_is_program(program_name: str) -> Optional[str]:
    '''
    This is the equivalent of shutil.which in Python 3.
    TODO: deduplicate. We have this function and also the which() function in __init__.py.
    '''
    path = os.getenv('PATH')
    assert path is not None
    for path_dir in path.split(os.path.pathsep):
        full_path = os.path.join(path_dir, program_name)
        if os.path.exists(full_path) and os.access(full_path, os.X_OK):
            return full_path
    return None


g_is_ninja_available: Optional[bool] = None


def is_ninja_available() -> bool:
    global g_is_ninja_available
    if g_is_ninja_available is None:
        g_is_ninja_available = bool(where_is_program('ninja'))
    return g_is_ninja_available


def compute_file_sha256(path: str) -> str:
    return hashsum_file(hashlib.sha256(), path)


def filter_and_join_strings(str_list: List[str], to_exclude: Set[str]) -> str:
    return ' '.join([s for s in str_list if s not in to_exclude])


DEVTOOLSET_ENV_VARS: Set[str] = set([s.strip() for s in """
    INFOPATH
    LD_LIBRARY_PATH
    MANPATH
    PATH
    PCP_DIR
    PERL5LIB
    PKG_CONFIG_PATH
    PYTHONPATH
""".strip().split("\n")])


def activate_devtoolset(devtoolset_number: int) -> None:
    devtoolset_enable_script = (
        '/opt/rh/devtoolset-%d/enable' % devtoolset_number
    )
    log("Enabling devtoolset-%s by sourcing the script %s",
        devtoolset_number, devtoolset_enable_script)
    if not os.path.exists(devtoolset_enable_script):
        raise IOError("Devtoolset script does not exist: %s" % devtoolset_enable_script)

    cmd_args = ['bash', '-c', '. "%s" && env' % devtoolset_enable_script]
    log("Running command: %s", cmd_args)
    devtoolset_env_str = subprocess.check_output(cmd_args).decode('utf-8')

    found_vars = set()
    for line in devtoolset_env_str.split("\n"):
        line = line.strip()
        if not line:
            continue
        k, v = line.split("=", 1)
        if k in DEVTOOLSET_ENV_VARS:
            log("Setting %s to: %s", k, v)
            os.environ[k] = v
            found_vars.add(k)
    missing_vars = set()
    for var_name in DEVTOOLSET_ENV_VARS:
        if var_name not in found_vars:
            log("Did not set env var %s for devtoolset-%d", var_name, devtoolset_number)
            missing_vars.add(var_name)
    if missing_vars:
        raise IOError(
            "Invalid environment after running devtoolset script %s. Did not set vars: %s" % (
                devtoolset_enable_script, ', '.join(sorted(missing_vars))
            ))


def get_rpath_flag(path: str) -> str:
    """
    Get the linker flag needed to add the given RPATH to the generated executable or library.
    """
    return "-Wl,-rpath,{}".format(path)


def sanitize_flags_line_for_log(line: str) -> str:
    return line.replace(PLACEHOLDER_RPATH, PLACEHOLDER_RPATH_FOR_LOG)


class Builder(BuilderInterface):
    args: argparse.Namespace
    cc: Optional[str]
    cxx: Optional[str]
    linuxbrew_dir: Optional[str]
    tp_download_dir: str
    ld_flags: List[str]
    compiler_flags: List[str]
    c_flags: List[str]
    cxx_flags: List[str]
    libs: List[str]

    """
    This class manages the overall process of building third-party dependencies, including the set
    of dependencies to build, build types, and the directories to install dependencies.
    """
    def __init__(self) -> None:
        self.tp_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
        self.tp_build_dir = os.path.join(self.tp_dir, 'build')
        self.tp_src_dir = os.path.join(self.tp_dir, 'src')
        self.tp_download_dir = os.path.join(self.tp_dir, 'download')
        self.tp_installed_dir = os.path.join(self.tp_dir, 'installed')
        self.tp_installed_common_dir = os.path.join(self.tp_installed_dir, BUILD_TYPE_COMMON)
        self.tp_installed_llvm7_common_dir = os.path.join(
                self.tp_installed_dir + '_llvm7', BUILD_TYPE_COMMON)
        self.src_dir = os.path.dirname(self.tp_dir)
        if not os.path.isdir(self.src_dir):
            fatal('YB src directory "{}" does not exist'.format(self.src_dir))

        self.linuxbrew_dir = None
        self.cc = None
        self.cxx = None

        self.load_expected_checksums()

    def set_compiler(self, compiler_type: str) -> None:
        if is_mac():
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

        if self.args.use_compiler_wrapper:
            os.environ['YB_THIRDPARTY_REAL_C_COMPILER'] = c_compiler
            os.environ['YB_THIRDPARTY_REAL_CXX_COMPILER'] = cxx_compiler
            os.environ['YB_THIRDPARTY_USE_CCACHE'] = '1' if self.args.use_ccache else '0'

            python_scripts_dir = os.path.join(YB_THIRDPARTY_DIR, 'python', 'yugabyte_db_thirdparty')
            os.environ['CC'] = os.path.join(python_scripts_dir, 'compiler_wrapper_cc.py')
            os.environ['CXX'] = os.path.join(python_scripts_dir, 'compiler_wrapper_cxx.py')
        else:
            os.environ['CC'] = c_compiler
            os.environ['CXX'] = cxx_compiler

    def parse_args(self) -> None:
        os.environ['YB_IS_THIRDPARTY_BUILD'] = '1'

        parser = argparse.ArgumentParser(prog=sys.argv[0])
        parser.add_argument('--build-type',
                            default=None,
                            type=str,
                            choices=BUILD_TYPES,
                            help='Build only specific part of thirdparty dependencies.')
        parser.add_argument('--skip-sanitizers',
                            action='store_true',
                            help='Do not build ASAN and TSAN instrumented dependencies.')
        parser.add_argument('--clean',
                            action='store_const',
                            const=True,
                            default=False,
                            help='Clean.')
        parser.add_argument('--add_checksum',
                            help='Compute and add unknown checksums to %s' % CHECKSUM_FILE_NAME,
                            action='store_true')
        parser.add_argument('--skip',
                            help='Dependencies to skip')

        parser.add_argument(
            '--single-compiler-type',
            type=str,
            choices=['gcc', 'clang'],
            default=None,
            help='Produce a third-party dependencies build using only a single compiler. '
                 'This also implies that we are not using Linuxbrew.')

        parser.add_argument(
            '--compiler-prefix',
            type=str,
            help='The prefix directory for looking for compiler executables. We will look for '
                 'compiler executable in the bin subdirectory of this directory.')

        parser.add_argument(
            '--compiler-suffix',
            type=str,
            default='',
            help='Suffix to append to compiler executables, such as the version number, '
                 'potentially prefixed with a dash, to obtain names such as gcc-8, g++-8, '
                 'clang-10, or clang++-10.')

        parser.add_argument(
            '--devtoolset',
            type=int,
            help='Specifies a CentOS devtoolset')

        parser.add_argument('-j', '--make-parallelism',
                            help='How many cores should the build use. This is passed to '
                                 'Make/Ninja child processes. This can also be specified using the '
                                 'YB_MAKE_PARALLELISM environment variable.',
                            type=int)

        parser.add_argument(
            '--use-ccache',
            action='store_true',
            help='Use ccache to speed up compilation')

        parser.add_argument(
            '--use-compiler-wrapper',
            action='store_true',
            help='Use a compiler wrapper script. Allows additional validation but '
                 'makes the build slower.')

        parser.add_argument(
            'dependencies',
            nargs=argparse.REMAINDER,
            help='Dependencies to build.')

        self.args = parser.parse_args()

        if self.args.dependencies and self.args.skip:
            raise ValueError(
                "--skip is not compatible with specifying a list of dependencies to build")

        if self.args.make_parallelism:
            os.environ['YB_MAKE_PARALLELISM'] = str(self.args.make_parallelism)

        # -----------------------------------------------------------------------------------------
        # Activate that devtoolset in CentOS 7 and use the GCC from it.
        # We only use GCC in this case.

        if is_mac():
            if self.args.single_compiler_type not in [None, 'clang']:
                raise ValueError("--single-compiler-type=%s is not allowed on macOS" %
                                 self.args.single_compiler_type)
            self.args.single_compiler_type = 'clang'

        if self.args.devtoolset is not None:
            if not is_centos():
                raise ValueError("--devtoolset can only be used on CentOS Linux")
            if self.args.single_compiler_type not in [None, 'gcc']:
                raise ValueError("--devtoolset is not compatible with compiler type: %s" %
                                 self.args.single_compiler_type)
            self.args.single_compiler_type = 'gcc'

    def use_only_clang(self) -> bool:
        return is_mac() or self.args.single_compiler_type == 'clang'

    def use_existing_clang_on_linux(self) -> bool:
        return self.args.single_compiler == 'clang'

    def use_only_gcc(self) -> bool:
        return bool(self.args.devtoolset) or self.args.single_compiler_type == 'gcc'

    def finish_initialization(self) -> None:
        self.detect_linuxbrew()
        self.populate_dependencies()
        self.select_dependencies_to_build()
        if self.args.devtoolset:
            activate_devtoolset(self.args.devtoolset)

    def populate_dependencies(self) -> None:
        # We have to use get_build_def_module to access submodules of build_definitions,
        # otherwise MyPy gets confused.

        self.dependencies = [
            get_build_def_module('zlib').ZLibDependency(),
            get_build_def_module('lz4').LZ4Dependency(),
            get_build_def_module('openssl').OpenSSLDependency(),
            get_build_def_module('libev').LibEvDependency(),
            get_build_def_module('rapidjson').RapidJsonDependency(),
            get_build_def_module('squeasel').SqueaselDependency(),
            get_build_def_module('curl').CurlDependency(),
            get_build_def_module('hiredis').HiRedisDependency(),
            get_build_def_module('cqlsh').CQLShDependency(),
            get_build_def_module('redis_cli').RedisCliDependency(),
            get_build_def_module('flex').FlexDependency(),
            get_build_def_module('bison').BisonDependency(),
            get_build_def_module('libedit').LibEditDependency(),
            get_build_def_module('openldap').OpenLDAPDependency(),
        ]

        if is_linux():
            self.dependencies += [
                get_build_def_module('libuuid').LibUuidDependency(),
            ]

            if not self.use_only_gcc():
                if not self.use_only_clang():
                    self.dependencies.append(get_build_def_module('llvm').LLVMDependency())
                self.dependencies.append(get_build_def_module('libcxx').LibCXXDependency())

            if self.use_only_clang():
                self.dependencies.extend([
                    get_build_def_module('llvm_libunwind').LlvmLibUnwindDependency(),
                    get_build_def_module('libcxx10').LibCxx10Dependency()
                ])
            else:
                self.dependencies.append(get_build_def_module('libunwind').LibUnwindDependency())

            self.dependencies.append(get_build_def_module('libbacktrace').LibBacktraceDependency())

        self.dependencies += [
            get_build_def_module('icu4c').Icu4cDependency(),
            get_build_def_module('protobuf').ProtobufDependency(),
            get_build_def_module('crypt_blowfish').CryptBlowfishDependency(),
            get_build_def_module('boost').BoostDependency(),

            get_build_def_module('gflags').GFlagsDependency(),
            get_build_def_module('glog').GLogDependency(),
            get_build_def_module('gperftools').GPerfToolsDependency(),
            get_build_def_module('gmock').GMockDependency(),
            get_build_def_module('snappy').SnappyDependency(),
            get_build_def_module('crcutil').CRCUtilDependency(),
            get_build_def_module('libcds').LibCDSDependency(),

            get_build_def_module('libuv').LibUvDependency(),
            get_build_def_module('cassandra_cpp_driver').CassandraCppDriverDependency(),
        ]

    def select_dependencies_to_build(self) -> None:
        self.selected_dependencies = []
        if self.args.dependencies:
            names = set([dep.name for dep in self.dependencies])
            for dep in self.args.dependencies:
                if dep not in names:
                    fatal("Unknown dependency name: %s", dep)
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

    def run(self) -> None:
        self.set_compiler('clang' if self.use_only_clang() else 'gcc')
        if self.args.clean:
            self.clean()
        self.prepare_out_dirs()
        self.curl_path = which('curl')
        os.environ['PATH'] = ':'.join([
                os.path.join(self.tp_installed_common_dir, 'bin'),
                os.path.join(self.tp_installed_llvm7_common_dir, 'bin'),
                os.environ['PATH']
        ])
        self.build(BUILD_TYPE_COMMON)
        if is_linux():
            self.build(BUILD_TYPE_UNINSTRUMENTED)
        if not self.use_only_gcc():
            if self.using_linuxbrew() or is_mac():
                self.build(BUILD_TYPE_CLANG_UNINSTRUMENTED)
            if is_linux() and not self.args.skip_sanitizers:
                self.build(BUILD_TYPE_ASAN)
                self.build(BUILD_TYPE_TSAN)

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
        if self.args.devtoolset:
            devtoolset_substring = '/devtoolset-%d/' % self.args.devtoolset
            if devtoolset_substring not in compiler_path:
                raise ValueError(
                    "Invalid compiler path: %s. Substring not found: %s" % (
                        compiler_path, devtoolset_substring))
        if not os.path.exists(compiler_path):
            raise IOError("Compiler does not exist: %s" % compiler_path)

    @overrides
    def get_c_compiler(self) -> str:
        assert self.cc is not None
        return self.cc

    @overrides
    def get_cxx_compiler(self) -> str:
        assert self.cxx is not None
        return self.cxx

    def find_gcc(self) -> Tuple[str, str]:
        return self.do_find_gcc('gcc', 'g++')

    def do_find_gcc(self, c_compiler: str, cxx_compiler: str) -> Tuple[str, str]:
        if self.using_linuxbrew():
            gcc_dir = self.get_linuxbrew_dir()
        elif self.args.compiler_prefix:
            gcc_dir = self.args.compiler_prefix
        else:
            return which(c_compiler), which(cxx_compiler)

        gcc_bin_dir = os.path.join(gcc_dir, 'bin')

        if not os.path.isdir(gcc_bin_dir):
            fatal("Directory {} does not exist".format(gcc_bin_dir))

        return (os.path.join(gcc_bin_dir, 'gcc') + self.args.compiler_suffix,
                os.path.join(gcc_bin_dir, 'g++') + self.args.compiler_suffix)

    def find_clang(self) -> Tuple[str, str]:
        clang_prefix: Optional[str] = None
        if self.args.compiler_prefix:
            clang_prefix = self.args.compiler_prefix
        else:
            candidate_dirs = [
                os.path.join(self.tp_dir, 'clang-toolchain'),
                '/usr'
            ]
            for dir in candidate_dirs:
                bin_dir = os.path.join(dir, 'bin')
                if os.path.exists(os.path.join(bin_dir, 'clang' + self.args.compiler_suffix)):
                    clang_prefix = dir
                    break
            if clang_prefix is None:
                fatal("Failed to find clang at the following locations: {}".format(candidate_dirs))

        assert clang_prefix is not None
        clang_bin_dir = os.path.join(clang_prefix, 'bin')

        return (os.path.join(clang_bin_dir, 'clang') + self.args.compiler_suffix,
                os.path.join(clang_bin_dir, 'clang++') + self.args.compiler_suffix)

    def detect_linuxbrew(self) -> None:
        if (not is_linux() or
                self.args.single_compiler_type or
                self.args.compiler_prefix or
                self.args.compiler_suffix):
            return

        self.linuxbrew_dir = os.getenv('YB_LINUXBREW_DIR')

        if self.linuxbrew_dir:
            os.environ['PATH'] = os.path.join(self.linuxbrew_dir, 'bin') + ':' + os.environ['PATH']

    def using_linuxbrew(self) -> bool:
        return self.linuxbrew_dir is not None

    def get_linuxbrew_dir(self) -> str:
        assert self.linuxbrew_dir is not None
        return self.linuxbrew_dir

    def clean(self) -> None:
        """
        TODO: deduplicate this vs. the clean_thirdparty.sh script.
        """
        heading('Clean')
        for dependency in self.selected_dependencies:
            for dir_name in BUILD_TYPES:
                for leaf in [dependency.name, '.build-stamp-{}'.format(dependency)]:
                    path = os.path.join(self.tp_build_dir, dir_name, leaf)
                    if os.path.exists(path):
                        log("Removing %s build output: %s", dependency.name, path)
                        remove_path(path)
            if dependency.dir_name is not None:
                src_dir = self.source_path(dependency)
                if os.path.exists(src_dir):
                    log("Removing %s source: %s", dependency.name, src_dir)
                    remove_path(src_dir)

            archive_path = self.archive_path(dependency)
            if archive_path is not None:
                log("Removing %s archive: %s", dependency.name, archive_path)
                remove_path(archive_path)

    def download_dependency(self, dep: Dependency) -> None:
        src_path = self.source_path(dep)
        patch_level_path = os.path.join(src_path, 'patchlevel-{}'.format(dep.patch_version))
        if os.path.exists(patch_level_path):
            return

        download_url = dep.download_url
        if download_url is None:
            download_url = CLOUDFRONT_URL.format(dep.archive_name)
            log("Using legacy download URL: %s (we should consider moving this to GitHub)",
                download_url)

        archive_path = self.archive_path(dep)

        remove_path(src_path)
        # If download_url is "mkdir" then we just create empty directory with specified name.
        if download_url != 'mkdir':
            if archive_path is None:
                return
            self.ensure_file_downloaded(download_url, archive_path)
            self.extract_archive(archive_path,
                                 os.path.dirname(src_path),
                                 os.path.basename(src_path))
        else:
            log("Creating %s", src_path)
            mkdir_if_missing(src_path)

        if hasattr(dep, 'extra_downloads'):
            for extra in dep.extra_downloads:
                assert extra.archive_name is not None
                archive_path = os.path.join(self.tp_download_dir, extra.archive_name)
                log("Downloading %s from %s", extra.archive_name, extra.download_url)
                self.ensure_file_downloaded(extra.download_url, archive_path)
                output_path = os.path.join(src_path, extra.dir_name)
                self.extract_archive(archive_path, output_path)
                if extra.post_exec is not None:
                    with PushDir(output_path):
                        assert isinstance(extra.post_exec, list)
                        if isinstance(extra.post_exec[0], str):
                            subprocess.check_call(cast(List[str], extra.post_exec))
                        else:
                            for command in extra.post_exec:
                                subprocess.check_call(command)

        if hasattr(dep, 'patches'):
            with PushDir(src_path):
                for patch in dep.patches:
                    log("Applying patch: %s", patch)
                    process = subprocess.Popen(['patch', '-p{}'.format(dep.patch_strip)],
                                               stdin=subprocess.PIPE)
                    with open(os.path.join(self.tp_dir, 'patches', patch), 'rt') as inp:
                        patch = inp.read()
                    assert process.stdin is not None
                    process.stdin.write(patch.encode('utf-8'))
                    process.stdin.close()
                    exit_code = process.wait()
                    if exit_code:
                        fatal("Patch {} failed with code: {}".format(dep.name, exit_code))
                if dep.post_patch:
                    subprocess.check_call(dep.post_patch)

        with open(patch_level_path, 'wb') as out:
            # Just create an empty file.
            pass

    def archive_path(self, dep: Dependency) -> Optional[str]:
        if dep.archive_name is None:
            return None
        return os.path.join(self.tp_download_dir, dep.archive_name)

    @overrides
    def source_path(self, dep: Dependency) -> str:
        return os.path.join(self.tp_src_dir, dep.dir_name)

    def get_checksum_file(self) -> str:
        return os.path.join(self.tp_dir, CHECKSUM_FILE_NAME)

    def load_expected_checksums(self) -> None:
        checksum_file = self.get_checksum_file()
        if not os.path.exists(checksum_file):
            fatal("Expected checksum file not found at {}".format(checksum_file))

        self.filename2checksum = {}
        with open(checksum_file, 'rt') as inp:
            for line in inp:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                sum, fname = line.split(None, 1)
                if not re.match('^[0-9a-f]{64}$', sum):
                    fatal("Invalid checksum: '%s' for archive name: '%s' in %s. Expected to be a "
                          "SHA-256 sum (64 hex characters).", sum, fname, checksum_file)
                self.filename2checksum[fname] = sum

    def get_expected_checksum(self, filename: str, downloaded_path: str) -> str:
        if filename not in self.filename2checksum:
            if self.args.add_checksum:
                checksum_file = self.get_checksum_file()
                with open(checksum_file, 'rt') as inp:
                    lines = inp.readlines()
                lines = [line.rstrip() for line in lines]
                checksum = compute_file_sha256(downloaded_path)
                lines.append("%s  %s" % (checksum, filename))
                with open(checksum_file, 'wt') as out:
                    for line in lines:
                        out.write(line + "\n")
                self.filename2checksum[filename] = checksum
                log("Added checksum for %s to %s: %s", filename, checksum_file, checksum)
                return checksum

            fatal("No expected checksum provided for {}".format(filename))
        return self.filename2checksum[filename]

    def ensure_file_downloaded(self, url: str, path: str) -> None:
        filename = os.path.basename(path)

        mkdir_if_missing(self.tp_download_dir)

        if os.path.exists(path):
            # We check the filename against our checksum map only if the file exists. This is done
            # so that we would still download the file even if we don't know the checksum, making it
            # easier to add new third-party dependencies.
            expected_checksum = self.get_expected_checksum(filename, downloaded_path=path)
            if self.verify_checksum(path, expected_checksum):
                log("No need to re-download %s: checksum already correct", filename)
                return
            log("File %s already exists but has wrong checksum, removing", path)
            remove_path(path)

        log("Fetching %s", filename)
        sleep_time_sec = INITIAL_DOWNLOAD_RETRY_SLEEP_TIME_SEC
        for attempt_index in range(1, MAX_FETCH_ATTEMPTS + 1):
            try:
                subprocess.check_call([self.curl_path, '-o', path, '--location', url])
                break
            except subprocess.CalledProcessError as ex:
                log("Error downloading %s (attempt %d): %s",
                    self.curl_path, attempt_index, str(ex))
                if attempt_index == MAX_FETCH_ATTEMPTS:
                    log("Giving up after %d attempts", MAX_FETCH_ATTEMPTS)
                    raise ex
                log("Will retry after %.1f seconds", sleep_time_sec)
                time.sleep(sleep_time_sec)
                sleep_time_sec += DOWNLOAD_RETRY_SLEEP_INCREASE_SEC

        if not os.path.exists(path):
            fatal("Downloaded '%s' but but unable to find '%s'", url, path)
        expected_checksum = self.get_expected_checksum(filename, downloaded_path=path)
        if not self.verify_checksum(path, expected_checksum):
            fatal("File '%s' has wrong checksum after downloading from '%s'. "
                  "Has %s, but expected: %s",
                  path, url, compute_file_sha256(path), expected_checksum)

    def verify_checksum(self, filename: str, expected_checksum: str) -> bool:
        real_checksum = hashsum_file(hashlib.sha256(), filename)
        return real_checksum == expected_checksum

    def extract_archive(
            self,
            archive_filename: str,
            out_dir: str,
            out_name: Optional[str] = None) -> None:
        """
        Extract the given archive into a subdirectory of out_dir, optionally renaming it to
        the specified name out_name. The archive is expected to contain exactly one directory.
        If out_name is not specified, the name of the directory inside the archive becomes
        the name of the destination directory.

        out_dir is the parent directory that should contain the extracted directory when the
        function returns.
        """

        def dest_dir_already_exists(full_out_path: str) -> bool:
            if os.path.exists(full_out_path):
                log("Directory already exists: %s, skipping extracting %s" % (
                        full_out_path, archive_filename))
                return True
            return False

        full_out_path = None
        if out_name:
            full_out_path = os.path.join(out_dir, out_name)
            if dest_dir_already_exists(full_out_path):
                return

        # Extract the archive into a temporary directory.
        tmp_out_dir = os.path.join(
            out_dir, 'tmp-extract-%s-%s-%d' % (
                os.path.basename(archive_filename),
                datetime.now().strftime('%Y-%m-%dT%H_%M_%S'),  # Current second-level timestamp.
                random.randint(10 ** 8, 10 ** 9 - 1)))  # A random 9-digit integer.
        if os.path.exists(tmp_out_dir):
            raise IOError("Just-generated unique directory name already exists: %s" % tmp_out_dir)
        os.makedirs(tmp_out_dir)

        archive_extension = None
        for ext in ARCHIVE_TYPES:
            if archive_filename.endswith(ext):
                archive_extension = ext
                break
        if not archive_extension:
            fatal("Unknown archive type for: {}".format(archive_filename))
        assert archive_extension is not None

        try:
            with PushDir(tmp_out_dir):
                cmd = ARCHIVE_TYPES[archive_extension].format(archive_filename)
                log("Extracting %s in temporary directory %s", cmd, tmp_out_dir)
                subprocess.check_call(cmd, shell=True)
                extracted_subdirs = [
                    subdir_name for subdir_name in os.listdir(tmp_out_dir)
                    if not subdir_name.startswith('.')
                ]
                if len(extracted_subdirs) != 1:
                    raise IOError(
                        "Expected the extracted archive %s to contain exactly one "
                        "subdirectory and no files, found: %s" % (
                            archive_filename, extracted_subdirs))
                extracted_subdir_basename = extracted_subdirs[0]
                extracted_subdir_path = os.path.join(tmp_out_dir, extracted_subdir_basename)
                if not os.path.isdir(extracted_subdir_path):
                    raise IOError(
                        "This is a file, expected it to be a directory: %s" %
                        extracted_subdir_path)

                if not full_out_path:
                    full_out_path = os.path.join(out_dir, extracted_subdir_basename)
                    if dest_dir_already_exists(full_out_path):
                        return

                log("Moving %s to %s", extracted_subdir_path, full_out_path)
                shutil.move(extracted_subdir_path, full_out_path)
        finally:
            log("Removing temporary directory: %s", tmp_out_dir)
            shutil.rmtree(tmp_out_dir)

    def prepare_out_dirs(self) -> None:
        dirs = [os.path.join(self.tp_installed_dir, type) for type in BUILD_TYPES]
        libcxx_dirs = [os.path.join(dir, 'libcxx') for dir in dirs]
        for dir in dirs + libcxx_dirs:
            lib_dir = os.path.join(dir, 'lib')
            mkdir_if_missing(lib_dir)
            mkdir_if_missing(os.path.join(dir, 'include'))
            # On some systems, autotools installs libraries to lib64 rather than lib.    Fix
            # this by setting up lib64 as a symlink to lib.    We have to do this step first
            # to handle cases where one third-party library depends on another.    Make sure
            # we create a relative symlink so that the entire PREFIX_DIR could be moved,
            # e.g. after it is packaged and then downloaded on a different build node.
            lib64_dir = os.path.join(dir, 'lib64')
            if os.path.exists(lib64_dir):
                if os.path.islink(lib64_dir):
                    continue
                remove_path(lib64_dir)
            os.symlink('lib', lib64_dir)

    def init_compiler_independent_flags(self, dep: Dependency) -> None:
        """
        Initialize compiler and linker flags for a particular build type. We try to limit this
        function to flags that will work for most compilers we are using, which include various
        versions of GCC and Clang.
        """
        self.preprocessor_flags = []
        self.ld_flags = []
        self.compiler_flags = []
        self.c_flags = []
        self.cxx_flags = []
        self.libs = []

        self.add_linuxbrew_flags()
        # -fPIC is there to always generate position-independent code, even for static libraries.
        self.preprocessor_flags.append(
            '-I{}'.format(os.path.join(self.tp_installed_common_dir, 'include')))
        self.compiler_flags += self.preprocessor_flags
        self.compiler_flags += ['-fno-omit-frame-pointer', '-fPIC', '-O2', '-Wall']
        self.ld_flags.append('-L{}'.format(os.path.join(self.tp_installed_common_dir, 'lib')))
        if is_linux():
            # On Linux, ensure we set a long enough rpath so we can change it later with chrpath or
            # a similar tool.
            self.add_rpath(PLACEHOLDER_RPATH)

            self.dylib_suffix = "so"
        elif is_mac():
            self.dylib_suffix = "dylib"

            # YugaByte builds with C++11, which on OS X requires using libc++ as the standard
            # library implementation. Some of the dependencies do not compile against libc++ by
            # default, so we specify it explicitly.
            self.cxx_flags.append("-stdlib=libc++")
            self.libs += ["-lc++", "-lc++abi"]

            # Build for macOS Mojave or later. See https://bit.ly/37myHbk
            self.compiler_flags.append("-mmacosx-version-min=10.14")
        else:
            fatal("Unsupported platform: {}".format(platform.system()))

        # The C++ standard must match CMAKE_CXX_STANDARD in the top-level CMakeLists.txt file in
        # the YugabyteDB source tree.
        self.cxx_flags.append('-std=c++14')

    def add_linuxbrew_flags(self) -> None:
        if self.using_linuxbrew():
            lib_dir = os.path.join(self.get_linuxbrew_dir(), 'lib')
            self.ld_flags.append(" -Wl,-dynamic-linker={}".format(os.path.join(lib_dir, 'ld.so')))
            self.add_lib_dir_and_rpath(lib_dir)

    def add_lib_dir_and_rpath(self, lib_dir: str) -> None:
        self.ld_flags.append("-L{}".format(lib_dir))
        self.add_rpath(lib_dir)

    def prepend_lib_dir_and_rpath(self, lib_dir: str) -> None:
        self.ld_flags.insert(0, "-L{}".format(lib_dir))
        self.prepend_rpath(lib_dir)

    def add_rpath(self, path: str) -> None:
        log("Adding RPATH: %s", path)
        self.ld_flags.append(get_rpath_flag(path))

    @overrides
    def prepend_rpath(self, path: str) -> None:
        self.ld_flags.insert(0, get_rpath_flag(path))

    @overrides
    def log_prefix(self, dep: Dependency) -> str:
        return '{} ({})'.format(dep.name, self.build_type)

    @overrides
    def build_with_configure(
            self,
            log_prefix: str,
            extra_args: List[str] = [],
            configure_cmd: List[str] = ['./configure'],
            install: List[str] = ['install'],
            run_autogen: bool = False,
            autoconf: bool = False,
            src_subdir_name: Optional[str] = None) -> None:
        os.environ["YB_REMOTE_COMPILATION"] = "0"
        dir_for_build = os.getcwd()
        if src_subdir_name:
            dir_for_build = os.path.join(dir_for_build, src_subdir_name)

        with PushDir(dir_for_build):
            log("Building in %s", dir_for_build)
            if run_autogen:
                log_output(log_prefix, ['./autogen.sh'])
            if autoconf:
                log_output(log_prefix, ['autoreconf', '-i'])

            configure_args = (
                configure_cmd.copy() + ['--prefix={}'.format(self.prefix)] + extra_args
            )
            log_output(log_prefix, configure_args)
            log_output(log_prefix, ['make', '-j{}'.format(get_make_parallelism())])
            if install:
                log_output(log_prefix, ['make'] + install)

    @overrides
    def build_with_cmake(
            self,
            dep: Dependency,
            extra_args: List[str] = [],
            use_ninja_if_available: bool = False,
            src_subdir_name: Optional[str] = None,
            extra_build_tool_args: List[str] = [],
            should_install: bool = True,
            install_targets: List[str] = ['install']) -> None:
        build_tool = 'make'
        if use_ninja_if_available:
            ninja_available = is_ninja_available()
            log('Ninja is %s', 'available' if ninja_available else 'unavailable')
            if ninja_available:
                build_tool = 'ninja'

        log("Building dependency %s using CMake. Build tool: %s", dep, build_tool)
        log_prefix = self.log_prefix(dep)
        os.environ["YB_REMOTE_COMPILATION"] = "0"

        remove_path('CMakeCache.txt')
        remove_path('CMakeFiles')

        src_path = self.source_path(dep)
        if src_subdir_name is not None:
            src_path = os.path.join(src_path, src_subdir_name)

        args = ['cmake', src_path]
        if build_tool == 'ninja':
            args += ['-G', 'Ninja']
        if extra_args is not None:
            args += extra_args

        log("CMake command line (one argument per line):\n%s" %
            "\n".join([(" " * 4 + sanitize_flags_line_for_log(line)) for line in args]))
        log_output(log_prefix, args)

        build_tool_cmd = [
            build_tool, '-j{}'.format(get_make_parallelism())
        ] + extra_build_tool_args

        log_output(log_prefix, build_tool_cmd)

        if should_install:
            log_output(log_prefix, [build_tool] + install_targets)

    def build(self, build_type: str) -> None:
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
            if dep.build_group == build_group and dep.should_build(self):
                self.build_dependency(dep)

    @overrides
    def get_prefix(self, qualifier: Optional[str] = None) -> str:
        return os.path.join(
            self.tp_installed_dir + ('_' + qualifier if qualifier else ''),
            self.build_type)

    def set_build_type(self, build_type: str) -> None:
        self.build_type = build_type
        self.find_prefix = self.tp_installed_common_dir
        self.prefix = self.get_prefix()
        if build_type != BUILD_TYPE_COMMON:
            self.find_prefix += ';' + self.prefix
        self.prefix_bin = os.path.join(self.prefix, 'bin')
        self.prefix_lib = os.path.join(self.prefix, 'lib')
        self.prefix_include = os.path.join(self.prefix, 'include')
        if self.building_with_clang():
            compiler = 'clang'
        else:
            compiler = 'gcc'
        self.set_compiler(compiler)
        heading("Building {} dependencies (compiler type: {})".format(
            build_type, self.compiler_type))
        log("Compiler type: %s", self.compiler_type)
        log("C compiler: %s", self.get_c_compiler())
        log("C++ compiler: %s", self.get_cxx_compiler())

    def init_flags(self, dep: Dependency) -> None:
        """
        Initializes compiler and linker flags.
        """
        self.init_compiler_independent_flags(dep)

        if is_mac() or not self.building_with_clang():
            # No further special setup is required for Clang on macOS, or for GCC on Linux.
            return

        # -----------------------------------------------------------------------------------------
        # Special setup for Clang on Linux.
        # -----------------------------------------------------------------------------------------

        is_libcxx = dep.name.startswith('libcxx')

        if not is_libcxx:
            if self.build_type == BUILD_TYPE_ASAN:
                self.compiler_flags += [
                    '-fsanitize=address',
                    '-fsanitize=undefined',
                    '-DADDRESS_SANITIZER'
                ]
            if self.build_type == BUILD_TYPE_TSAN:
                self.compiler_flags += ['-fsanitize=thread', '-DTHREAD_SANITIZER']

        if self.args.single_compiler_type == 'clang':
            self.init_clang10_or_later_flags(dep)
            return

        # This is used to build code with libc++ and Clang 7 built as part of thirdparty.
        stdlib_suffix = self.build_type
        stdlib_path = os.path.join(self.tp_installed_dir, stdlib_suffix, 'libcxx')
        stdlib_include = os.path.join(stdlib_path, 'include', 'c++', 'v1')
        stdlib_lib = os.path.join(stdlib_path, 'lib')
        self.cxx_flags.insert(0, '-nostdinc++')
        self.cxx_flags.insert(0, '-isystem')
        self.cxx_flags.insert(1, stdlib_include)
        self.cxx_flags.insert(0, '-stdlib=libc++')
        # Clang complains about argument unused during compilation: '-stdlib=libc++' when both
        # -stdlib=libc++ and -nostdinc++ are specified.
        self.cxx_flags.insert(0, '-Wno-error=unused-command-line-argument')
        self.prepend_lib_dir_and_rpath(stdlib_lib)
        if self.using_linuxbrew():
            # This is needed when using Clang 7 built with Linuxbrew GCC, which we are still using
            # as of 10/2020.
            self.compiler_flags.append('--gcc-toolchain={}'.format(self.get_linuxbrew_dir()))

    def init_clang10_or_later_flags(self, dep: Dependency) -> None:
        """
        Flags for Clang 10 and beyond. We are using LLVM-supplied libunwind and compiler-rt in this
        configuration.
        """
        self.ld_flags.append('-rtlib=compiler-rt')

        if self.build_type != BUILD_TYPE_COMMON:
            is_libcxx = dep.name.startswith('libcxx')
            self.ld_flags += ['-lunwind']

            # TODO: dedup with the similar code above used for Clang 7.
            stdlib_suffix = self.build_type
            stdlib_path = os.path.join(self.tp_installed_dir, stdlib_suffix, 'libcxx10')
            stdlib_include = os.path.join(stdlib_path, 'include', 'c++', 'v1')
            stdlib_lib = os.path.join(stdlib_path, 'lib')

            if not is_libcxx:
                self.libs += ['-lc++', '-lc++abi']

                self.cxx_flags.insert(0, '-nostdinc++')
                self.cxx_flags.insert(0, '-isystem')
                self.cxx_flags.insert(1, stdlib_include)
                self.cxx_flags.insert(0, '-stdlib=libc++')

        # Needed for Cassandra C++ driver.
        # TODO mbautin: only specify these flags when building the Cassandra C++ driver.
        self.cxx_flags.insert(0, '-Wno-error=unused-command-line-argument')
        self.cxx_flags.insert(0, '-Wno-error=deprecated-declarations')

        # After linking every library or executable, we will check if it depends on libstdc++ and
        # fail immediately at that point.
        os.environ['YB_THIRDPARTY_DISALLOW_LIBSTDCXX'] = '1'

    def log_and_set_env_var(self, env_var_name: str, items: List[str]) -> None:
        value_str = ' '.join(items)
        log('Setting env var %s to %s', env_var_name, value_str)
        os.environ[env_var_name] = value_str

    def get_effective_cxx_flags(self, dep: Dependency) -> List[str]:
        dep_additional_cxx_flags = (dep.get_additional_cxx_flags(self) +
                                    dep.get_additional_c_cxx_flags(self))
        return self.compiler_flags + self.cxx_flags + dep_additional_cxx_flags

    def get_effective_c_flags(self, dep: Dependency) -> List[str]:
        dep_additional_c_flags = (dep.get_additional_c_flags(self) +
                                  dep.get_additional_c_cxx_flags(self))
        return self.compiler_flags + self.c_flags + dep_additional_c_flags

    def get_effective_ld_flags(self, dep: Dependency) -> List[str]:
        return list(self.ld_flags)

    @overrides
    def get_common_cmake_flag_args(self, dep: Dependency) -> List[str]:
        cxx_flags_str = ' '.join(self.get_effective_cxx_flags(dep))
        ld_flags_str = ' '.join(self.get_effective_ld_flags(dep))
        return [
            '-DCMAKE_CXX_FLAGS={}'.format(cxx_flags_str),
            '-DCMAKE_SHARED_LINKER_FLAGS={}'.format(ld_flags_str),
            '-DCMAKE_EXE_LINKER_FLAGS={}'.format(ld_flags_str)
        ]

    def build_dependency(self, dep: Dependency) -> None:
        if not self.should_rebuild_dependency(dep):
            return

        self.init_flags(dep)
        # This is needed at least for glog to be able to find gflags.
        self.add_rpath(os.path.join(self.tp_installed_dir, self.build_type, 'lib'))
        if self.build_type != BUILD_TYPE_COMMON:
            # Needed to find libunwind for Clang 10 when using compiler-rt.
            self.add_rpath(os.path.join(self.tp_installed_dir, BUILD_TYPE_COMMON, 'lib'))

        log("")
        colored_log(YELLOW_COLOR, SEPARATOR)
        colored_log(YELLOW_COLOR, "Building %s (%s)", dep.name, self.build_type)
        colored_log(YELLOW_COLOR, SEPARATOR)

        self.download_dependency(dep)

        self.log_and_set_env_var('CXXFLAGS', self.get_effective_cxx_flags(dep))
        self.log_and_set_env_var('CFLAGS', self.get_effective_c_flags(dep))
        self.log_and_set_env_var('LDFLAGS', self.get_effective_ld_flags(dep))
        self.log_and_set_env_var('LIBS', self.libs)
        self.log_and_set_env_var(
            'CPPFLAGS',
            [flag for flag in self.compiler_flags if flag.startswith('-I')])
        os.environ["CPPFLAGS"] = " ".join(self.preprocessor_flags)

        with PushDir(self.create_build_dir_and_prepare(dep)):
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
        stamp_path = self.get_build_stamp_path_for_dependency(dep)
        old_build_stamp = None
        if os.path.exists(stamp_path):
            with open(stamp_path, 'rt') as inp:
                old_build_stamp = inp.read()

        new_build_stamp = self.get_build_stamp_for_dependency(dep)

        if dep.dir_name is not None:
            src_dir = self.source_path(dep)
            if not os.path.exists(src_dir):
                log("Have to rebuild %s (%s): source dir %s does not exist",
                    dep.name, self.build_type, src_dir)
                return True

        if old_build_stamp == new_build_stamp:
            log("Not rebuilding %s (%s) -- nothing changed.", dep.name, self.build_type)
            return False
        else:
            log("Have to rebuild %s (%s):", dep.name, self.build_type)
            log("Old build stamp for %s (from %s):\n%s",
                dep.name, stamp_path, indent_lines(old_build_stamp))
            log("New build stamp for %s:\n%s",
                dep.name, indent_lines(new_build_stamp))
            return True

    def get_build_stamp_path_for_dependency(self, dep: Dependency) -> str:
        return os.path.join(self.tp_build_dir, self.build_type, '.build-stamp-{}'.format(dep.name))

    # Come up with a string that allows us to tell when to rebuild a particular third-party
    # dependency. The result is returned in the get_build_stamp_for_component_rv variable, which
    # should have been made local by the caller.
    def get_build_stamp_for_dependency(self, dep: Dependency) -> str:
        input_files_for_stamp = ['yb_build_thirdparty_main.py',
                                 'build_thirdparty.sh',
                                 os.path.join('build_definitions',
                                              '{}.py'.format(dep.name.replace('-', '_')))]

        for path in input_files_for_stamp:
            abs_path = os.path.join(self.tp_dir, path)
            if not os.path.exists(abs_path):
                fatal("File '%s' does not exist -- expecting it to exist when creating a 'stamp' "
                      "for the build configuration of '%s'.", abs_path, dep.name)

        with PushDir(self.tp_dir):
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
        stamp_path = self.get_build_stamp_path_for_dependency(dep)

        log("Saving new build stamp to '%s':\n%s", stamp_path, indent_lines(stamp))
        with open(stamp_path, "wt") as out:
            out.write(stamp)

    def create_build_dir_and_prepare(self, dep: Dependency) -> str:
        src_dir = self.source_path(dep)
        if not os.path.isdir(src_dir):
            fatal("Directory '{}' does not exist".format(src_dir))

        build_dir = os.path.join(self.tp_build_dir, self.build_type, dep.dir_name)
        mkdir_if_missing(build_dir)

        if dep.copy_sources:
            log("Bootstrapping %s from %s", build_dir, src_dir)
            subprocess.check_call(['rsync', '-a', src_dir + '/', build_dir])
        return build_dir

    @overrides
    def is_release_build(self) -> bool:
        """
        Distinguishes between build types that are potentially used in production releases from
        build types that are only used in testing (e.g. ASAN+UBSAN, TSAN).
        """
        return self.build_type in [
            BUILD_TYPE_COMMON, BUILD_TYPE_UNINSTRUMENTED, BUILD_TYPE_CLANG_UNINSTRUMENTED
        ]

    @overrides
    def cmake_build_type_for_test_only_dependencies(self) -> str:
        return 'Release' if self.is_release_build() else 'Debug'

    @overrides
    def building_with_clang(self) -> bool:
        """
        Returns true if we are using clang to build current build_type.
        """
        if self.use_only_clang():
            return True
        if self.use_only_gcc():
            return False

        return self.build_type in [
            BUILD_TYPE_ASAN,
            BUILD_TYPE_TSAN,
            BUILD_TYPE_CLANG_UNINSTRUMENTED
        ]

    @overrides
    def will_need_clang(self) -> bool:
        """
        Returns true if we will need Clang to complete the full thirdparty build type requested by
        the user.
        """
        if self.use_only_gcc():
            return False
        return self.args.build_type != BUILD_TYPE_UNINSTRUMENTED

    def check_cxx_compiler_flag(self, flag: str) -> bool:
        process = subprocess.Popen(
            [self.get_cxx_compiler(), '-x', 'c++', flag, '-'],
            stdin=subprocess.PIPE)
        assert process.stdin is not None
        process.stdin.write("int main() { return 0; }".encode('utf-8'))
        process.stdin.close()
        return process.wait() == 0

    @overrides
    def add_checked_flag(self, flags: List[str], flag: str) -> None:
        if self.check_cxx_compiler_flag(flag):
            flags.append(flag)

    @overrides
    def get_openssl_dir(self) -> str:
        return os.path.join(self.tp_installed_common_dir)

    @overrides
    def get_openssl_related_cmake_args(self) -> List[str]:
        """
        Returns a list of CMake arguments to use to pick up the version of OpenSSL that we should be
        using. Returns an empty list if the default OpenSSL installation should be used.
        """
        openssl_dir = self.get_openssl_dir()
        openssl_options = ['-DOPENSSL_ROOT_DIR=' + openssl_dir]
        openssl_crypto_library = os.path.join(openssl_dir, 'lib', 'libcrypto.' + self.dylib_suffix)
        openssl_ssl_library = os.path.join(openssl_dir, 'lib', 'libssl.' + self.dylib_suffix)
        openssl_options += [
            '-DOPENSSL_CRYPTO_LIBRARY=' + openssl_crypto_library,
            '-DOPENSSL_SSL_LIBRARY=' + openssl_ssl_library,
            '-DOPENSSL_LIBRARIES=%s;%s' % (openssl_crypto_library, openssl_ssl_library)
        ]
        return openssl_options


def main() -> None:
    unset_env_var_if_set('CC')
    unset_env_var_if_set('CXX')

    if 'YB_BUILD_THIRDPARTY_DUMP_ENV' in os.environ:
        heading('Environment of {}:'.format(sys.argv[0]))
        for key in os.environ:
            log('{}={}'.format(key, os.environ[key]))
        log_separator()

    builder = Builder()
    builder.parse_args()
    builder.finish_initialization()
    builder.run()

    # Check that the executables and libraries we have built don't depend on any unexpected dynamic
    # libraries installed on this system.
    get_lib_tester().run()


if __name__ == "__main__":
    main()
