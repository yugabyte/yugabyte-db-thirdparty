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

import json
import logging
import os
import random
import string
import subprocess
import copy
import re
import time

from collections import defaultdict
from datetime import datetime

from typing import Optional, DefaultDict, Tuple, List, Dict, cast, Union, Any, Set, Callable

from yugabyte_db_thirdparty import util, constants
from yugabyte_db_thirdparty.custom_logging import log


COMPILE_COMMAND_FILE_SUFFIX = '.compile_command.json'

TMP_DIR_ENV_VAR_NAME = 'YB_THIRDPARTY_COMPILE_COMMANDS_TMP_DIR'

SOURCE_FILE_SUFFIXES = ('.h', '.hpp', '.cc', '.c', '.cxx')

# The build directory has this subdirectory where we store the final compile_commands.json file.
COMPILE_COMMANDS_SUBDIR = 'yb_compile_commands'


def named_path_component_re_str(group_name: str) -> str:
    return r'(?P<%s>[^/]+)' % group_name


BAZEL_SANDBOX_PATH_RE_PREFIX_STR = '/'.join([
    r'^.*',
    r'[.]cache',
    r'.*',
    r'sandbox',
    r'linux-sandbox',
    r'[0-9]+',
    r'execroot',
    named_path_component_re_str('main_project')
])

REL_PATH_SUFFIX_RE_STR = '(?:|/(?P<rel_path>.*))'

EXTERNAL_REL_PATH_RE_STR = '/'.join([
    'external',
    named_path_component_re_str('external_project')
]) + REL_PATH_SUFFIX_RE_STR + '$'

BAZEL_SANDBOX_PATH_RE = re.compile(BAZEL_SANDBOX_PATH_RE_PREFIX_STR + REL_PATH_SUFFIX_RE_STR + '$')
BAZEL_SANDBOX_EXTERNAL_PATH_RE = re.compile(
    BAZEL_SANDBOX_PATH_RE_PREFIX_STR + '/' + EXTERNAL_REL_PATH_RE_STR)
EXTERNAL_REL_PATH_RE = re.compile('^' + EXTERNAL_REL_PATH_RE_STR)

INCLUDE_DIR_ARGS = ['-I', '-isystem', '-iquote']


def get_compile_command_path_for_output_file(
        tmp_dir: str,
        output_path: str) -> str:
    return tmp_dir + '/' + output_path + COMPILE_COMMAND_FILE_SUFFIX


def get_compile_commands_dir(build_dir: str) -> str:
    return os.path.join(build_dir, COMPILE_COMMANDS_SUBDIR)


def get_final_compile_commands_path(build_dir: str, raw: bool) -> str:
    return os.path.join(
        get_compile_commands_dir(build_dir), 'compile_commands%s.json' % ('_raw' if raw else ''))


def should_include_compile_command(compile_command: Dict[str, Union[str, List[str]]]) -> bool:
    file_path = cast(str, compile_command['file'])
    file_basename = os.path.basename(file_path)
    dir_path = cast(str, compile_command['directory'])
    dir_basename = os.path.basename(dir_path)
    return not file_basename == 'conftest.c' and dir_basename not in ['conftest', 'conftest.dir']


def filter_compile_commands(
        compile_commands: List[Dict[str, Union[str, List[str]]]]
        ) -> List[Dict[str, Union[str, List[str]]]]:
    return [c for c in compile_commands if should_include_compile_command(c)]


def aggregate_compile_commands(
        tmp_dir: str,
        build_dir: str,
        bazel_path_mapping: Dict[str, str],
        clang_toolchain_dir: Optional[str]) -> None:
    """
    Aggregate individual compilation command files into a single compile_commands.json file in the
    given directory.
    """
    compile_command_paths = subprocess.check_output([
        'find',
        tmp_dir,
        '-name',
        '*' + COMPILE_COMMAND_FILE_SUFFIX
    ]).decode('utf-8').splitlines()
    compile_command_paths = [p.strip() for p in compile_command_paths if p.strip()]

    # Put our compile_commands.json file in a separate directory to avoid confusion with the
    # CMake-generated compile_commands.json file, which might be at the root of the build
    # directory.
    compile_commands_dir = get_compile_commands_dir(build_dir)
    aggregated_path_raw = get_final_compile_commands_path(build_dir, raw=True)

    compile_commands = []
    for compile_command_path in compile_command_paths:
        with open(compile_command_path, 'r') as compile_command_file:
            compile_commands.append(json.load(compile_command_file))

    util.mkdir_p(compile_commands_dir)

    existing_compile_commands: List[Dict[str, Union[str, List[str]]]] = []

    if os.path.exists(aggregated_path_raw):
        existing_compile_commands = cast(List[Dict[str, Union[str, List[str]]]],
                                         util.read_json_file(aggregated_path_raw))

    new_files = set(c['file'] for c in compile_commands)

    # Merge the existing compile commands with the new ones.
    for existing_compile_command in existing_compile_commands:
        if existing_compile_command['file'] not in new_files:
            compile_commands.append(existing_compile_command)

    compile_commands = filter_compile_commands(compile_commands)

    compile_commands = sorted(compile_commands, key=lambda c: c['file'])
    with open(aggregated_path_raw, 'w') as compile_commands_file:
        json.dump(compile_commands, compile_commands_file, indent=2)
    logging.info(
        f"Generated a raw compilation commands file at {aggregated_path_raw} with "
        f"{len(compile_commands)} commands")

    # The individual compilation command files are no longer needed.
    for compile_command_path in compile_command_paths:
        os.remove(compile_command_path)

    postprocess_compile_commands(build_dir, bazel_path_mapping, clang_toolchain_dir)


def map_build_dir_to_source_dir(
        path: str, build_dir_to_src_dir_mapping_cache: Dict[str, str]) -> str:
    if not os.path.isabs(path):
        return path

    path_prefix = path
    considered_candidates = []
    while path_prefix.startswith(util.YB_THIRDPARTY_DIR + '/'):
        src_dir = None
        if path_prefix in build_dir_to_src_dir_mapping_cache:
            src_dir = build_dir_to_src_dir_mapping_cache[path_prefix]
        else:
            src_path_file_path = os.path.join(path_prefix, constants.SRC_PATH_FILE_NAME)
            if os.path.exists(src_path_file_path):
                src_dir = util.read_file(src_path_file_path).strip()
                build_dir_to_src_dir_mapping_cache[path_prefix] = src_dir
        if src_dir:
            candidate_path = util.join_paths_safe(src_dir, os.path.relpath(path, path_prefix))
            if os.path.exists(candidate_path):
                return candidate_path
            considered_candidates.append(candidate_path)

        path_prefix = os.path.dirname(path_prefix)
    return path


def rewrite_path(
        path: str,
        bazel_path_mapping: Dict[str, str],
        build_dir_to_src_dir_mapping_cache: Optional[Dict[str, str]]) -> str:
    """
    Rewrites the given path.
    :param path: The path to rewrite.
    :param bazel_path_mapping: the mapping of relative directories that Bazel creates in the build
        directory for each project to the build directories of these projects.
    :param build_dir_to_src_dir_mapping_cache: a cache of build directory to source directory path
        mapping. If this is None, we disable rewriting of paths from build to source directory,
        allowing the caller finer control, because such rewriting is not always needed.
    """
    new_path = path

    for external_project_re in [BAZEL_SANDBOX_EXTERNAL_PATH_RE, EXTERNAL_REL_PATH_RE]:
        m = external_project_re.match(path)
        if m:
            group_dict = m.groupdict()
            external_project = group_dict['external_project']
            project_build_dir = bazel_path_mapping.get(external_project)
            if project_build_dir:
                new_path = util.join_paths_safe(
                    project_build_dir,
                    group_dict['rel_path']
                )

    m = BAZEL_SANDBOX_PATH_RE.match(new_path)
    if m:
        group_dict = m.groupdict()
        new_path = util.join_paths_safe(
            bazel_path_mapping[group_dict['main_project']],
            group_dict['rel_path'])

    if build_dir_to_src_dir_mapping_cache is not None:
        new_path = map_build_dir_to_source_dir(new_path, build_dir_to_src_dir_mapping_cache)
    return new_path


def rewrite_arguments(
        args: List[str],
        work_dir: str,
        rewrite_path_fn: Callable[[str], str]) -> List[str]:
    # Separate arguments such as -I, -iquote, -isystem, from the path that follows them.
    normalized_args = []
    for arg in args:
        appended = False
        for prefix in INCLUDE_DIR_ARGS:
            if arg.startswith(prefix) and arg != prefix:
                normalized_args.append(prefix)
                normalized_args.append(arg[len(prefix):])
                appended = True

                break
        if not appended:
            normalized_args.append(arg)

    prev_arg = None
    new_args = []

    include_dirs_by_type: DefaultDict[str, Set[str]] = defaultdict(set)
    original_include_dirs_by_type: Dict[str, Set[str]] = {}

    for arg in normalized_args:
        # It is important to rewrite the path before converting it to an absolute one, because our
        # path rewriting logic relies on the path being relative, e.g. starting with "external".
        new_arg = rewrite_path_fn(arg)

        if prev_arg in INCLUDE_DIR_ARGS:
            if not os.path.isabs(arg):
                # It is important to use join_paths_safe in case the relative path is just ".".
                # Also rewrite the absolute path one more time.
                new_arg = rewrite_path_fn(util.join_paths_safe(work_dir, arg))

            # You would think MyPy would figure this out from the "if" condition.
            assert prev_arg is not None

            include_dirs_by_type[prev_arg].add(new_arg)
            original_include_dirs_by_type.setdefault(prev_arg, set()).add(arg)
        new_args.append(new_arg)
        prev_arg = arg

    # Append original include directories so we can still find any generated headers.
    for arg_type, include_dirs in original_include_dirs_by_type.items():
        for include_dir in include_dirs:
            if include_dir not in include_dirs_by_type[arg_type]:
                include_dirs_by_type[arg_type].add(include_dir)
                new_args.extend([arg_type, rewrite_path_fn(include_dir)])

    return new_args


def rewrite_compile_command(
        cmd: Dict[str, Any],
        bazel_path_mapping: Dict[str, str],
        build_dir_to_src_dir_mapping_cache: Dict[str, str]) -> Dict[str, str]:
    new_cmd = copy.deepcopy(cmd)

    # Do not rewrite the working directory path from build to source directory.
    new_cmd['directory'] = rewrite_path(
        new_cmd['directory'], bazel_path_mapping, build_dir_to_src_dir_mapping_cache=None)

    new_cmd['file'] = rewrite_path(
        new_cmd['file'], bazel_path_mapping, build_dir_to_src_dir_mapping_cache)

    new_cmd['arguments'] = rewrite_arguments(
        new_cmd['arguments'], new_cmd['directory'],
        rewrite_path_fn=lambda path: rewrite_path(
            path, bazel_path_mapping, build_dir_to_src_dir_mapping_cache))
    if new_cmd['file'].endswith(('.cc', '.cpp')) and new_cmd['arguments'][0].endswith('/clang'):
        # Sometimes Bazel might generate compilation commands that use the clang executable
        # to build C++ code. Make sure we use the clang++ executable instead.
        new_cmd['arguments'][0] += '++'
    if 'source_file_mapping' in new_cmd:
        del new_cmd['source_file_mapping']
    return new_cmd


def postprocess_compile_commands(
        build_dir: str,
        bazel_path_mapping: Dict[str, str],
        clang_toolchain_dir: Optional[str]) -> None:
    compile_commands_path_raw = get_final_compile_commands_path(build_dir, raw=True)
    if not os.path.exists(compile_commands_path_raw):
        log("File not found: %s, skipping", compile_commands_path_raw)
        return

    compile_commands = util.read_json_file(compile_commands_path_raw)
    new_compile_commands = []
    build_dir_to_src_dir_mapping_cache: Dict[str, str] = {}
    for compile_command in compile_commands:
        new_compile_commands.append(
            rewrite_compile_command(
                cast(Dict[str, Union[str, List[str]]], compile_command),
                bazel_path_mapping,
                build_dir_to_src_dir_mapping_cache
            ))

    compile_commands_path = get_final_compile_commands_path(build_dir, raw=False)
    logging.info(f"Generated the compilation commands file at {compile_commands_path}")

    with open(compile_commands_path, 'w') as compile_commands_file:
        json.dump(new_compile_commands, compile_commands_file, indent=2)

    create_vscode_settings(build_dir, clang_toolchain_dir)


def create_vscode_settings(build_dir: str, clang_toolchain_dir: Optional[str]) -> None:
    vscode_dir = os.path.join(build_dir, '.vscode')
    util.mkdir_p(vscode_dir)
    settings_json_path = os.path.join(vscode_dir, 'settings.json')
    compile_commands_subdir_path = os.path.join(build_dir, COMPILE_COMMANDS_SUBDIR)
    compile_commands_path = os.path.join(compile_commands_subdir_path, 'compile_commands.json')
    clangd_index_rel_path = os.path.join(COMPILE_COMMANDS_SUBDIR, 'clangd_index.binary')
    clangd_index_path = os.path.join(build_dir, clangd_index_rel_path)
    if not os.path.exists(settings_json_path) and clang_toolchain_dir is not None:
        settings = {
            'clangd.path': os.path.join(clang_toolchain_dir, 'bin', 'clangd'),
            'clangd.arguments': [
                "--header-insertion=never",
                "--compile-commands-dir=${workspaceFolder}/%s" % COMPILE_COMMANDS_SUBDIR,
                "--index-file=${workspaceFolder}/%s" % clangd_index_rel_path,
                "--background-index=false",
            ]
        }
        util.write_json_file(settings_json_path, settings)

    if clang_toolchain_dir is not None:
        clangd_index_stderr_path = os.path.join(compile_commands_subdir_path, 'clangd-indexer.log')

        clangd_indexer_cmd = [
            os.path.join(clang_toolchain_dir, 'bin', 'clangd-indexer'),
            '--executor=all-TUs',
            '--format=binary',
            compile_commands_path,
        ]

        clangd_indexer_script_path = os.path.join(compile_commands_subdir_path, 'clangd-indexer.sh')
        with open(clangd_indexer_script_path, 'w') as clangd_indexer_file:
            clangd_indexer_file.write('\n'.join([
                '#!/usr/bin/env bash',
                'set -euo pipefail',
                util.shlex_join(clangd_indexer_cmd),
            ]) + '\n')
        os.chmod(clangd_indexer_script_path, 0o755)

        start_time_sec = time.time()
        with open(clangd_index_path, 'w') as clangd_index_file:
            with open(clangd_index_stderr_path, 'w') as clangd_index_stderr_file:
                return_code = subprocess.call(
                    clangd_indexer_cmd, stdout=clangd_index_file, stderr=clangd_index_stderr_file)
        elapsed_time_sec = time.time() - start_time_sec
        if return_code != 0:
            log("clangd-indexer failed in %.1f seconds with return code %d, see %s for details",
                elapsed_time_sec, return_code, clangd_index_stderr_path)
        else:
            log("Generated clangd index in %.1f seconds at %s, see %s for details",
                elapsed_time_sec, clangd_index_path, clangd_index_stderr_path)


def get_compile_commands_tmp_dir_path(dep_name: str) -> str:
    """
    Our compiler wrapper will put per-file compilation commands in this directory.
    """
    return '-'.join([
        '/tmp/yb-compile-commands-tmp',
        dep_name,
        datetime.now().strftime('%Y-%m-%dT%H_%M_%S'),
        ''.join([random.choice(string.ascii_lowercase) for _ in range(16)])
    ])


def get_tmp_dir_env_var() -> Optional[str]:
    return os.environ.get(TMP_DIR_ENV_VAR_NAME)
