#!/usr/bin/env python3

"""
Checks Python code in this repository using various methods (MyPy, importing modules, syntax
checks, pycodestyle). Runs multiple checks in parallel.
"""

import concurrent.futures
import urllib.request
import glob
import os
import sys
import subprocess
import time

from typing import List, Union, Dict
from yugabyte_db_thirdparty.util import YB_THIRDPARTY_DIR


CHECK_TYPES = [
    'mypy',
    'compile',
    'import',
    'pycodestyle',
    'doctest',
]


def ensure_decoded(s: Union[str, bytes]) -> str:
    if isinstance(s, bytes):
        return s.decode('utf-8')
    return s


def increment_counter(d: Dict[str, int], key: str) -> None:
    if key in d:
        d[key] += 1
    else:
        d[key] = 1


def print_stats(description: str, d: Dict[str, int]) -> None:
    print("%s:\n    %s" % (
        description,
        '\n    '.join('%s: %s' % (k, v) for k, v in sorted(d.items()))
    ))


def rel_to_repo_root(file_path: str) -> str:
    return os.path.relpath(os.path.realpath(file_path), os.path.realpath(YB_THIRDPARTY_DIR))


class CheckResult:
    def __init__(
            self,
            check_type: str,
            file_path: str,
            cmd_args: List[str] = [],
            stdout: str = '',
            stderr: str = '',
            returncode: int = 0):
        self.check_type = check_type
        self.cmd_args = cmd_args
        self.file_path = file_path
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def get_description(self) -> str:
        return "Check '%s' for %s" % (self.check_type, rel_to_repo_root(self.file_path))


class Reporter:
    def __init__(self, line_width: int):
        self.line_width = line_width

    def write(self, line: str) -> None:
        sys.stdout.write(line)

    def print(self, line: str) -> None:
        self.write(line + '\n')

    def get_horizontal_line(self) -> str:
        return '-' * self.line_width + '\n'

    def print_check_result(self, check_result: CheckResult) -> None:
        if check_result.returncode == 0:
            return

        s = ''
        s += self.get_horizontal_line()
        s += check_result.get_description() + '\n'
        s += self.get_horizontal_line()
        s += 'Exit code: %d\n' % check_result.returncode

        if check_result.stdout.strip():
            s += '\n'
            s += 'Standard output:\n'
            s += check_result.stdout

        if check_result.stderr.strip():
            s += '\n'
            s += 'Standard error:\n'
            s += '\n'
            s += check_result.stderr

        s += '\n'
        self.write(s)


def check_file(file_path: str, check_type: str) -> CheckResult:
    assert check_type in CHECK_TYPES

    if check_type == 'mypy':
        args = ['mypy', '--config-file', 'mypy.ini']
    elif check_type == 'compile':
        args = ['python3', '-m', 'py_compile']
    elif check_type == 'import':
        rel_path = rel_to_repo_root(file_path)
        where_to_import_from = None
        what_to_import = None
        if rel_path.startswith('python/yugabyte_db_thirdparty/'):
            where_to_import_from = 'yugabyte_db_thirdparty'
            # Assuming a one-level hierarchy, i.e. that the yugabyte_db_thirdparty directory does
            # not contain any module subdirectories with Python files.
        elif rel_path.startswith('build_definitions/'):
            where_to_import_from = 'build_definitions'
        else:
            return CheckResult(check_type=check_type, file_path=file_path)

        args = [
            'python3', '-c', 'from %s import %s' % (
                where_to_import_from,
                os.path.splitext(os.path.basename(file_path))[0]
            )
        ]
    elif check_type == 'pycodestyle':
        args = ['pycodestyle',
                '--config=%s' % os.path.join(YB_THIRDPARTY_DIR, 'pycodestyle.cfg')]
    elif check_type == 'doctest':
        args = ['python3', '-m', 'doctest']
    else:
        raise ValueError(f"Unknown check type: {check_type}")
    args.append(file_path)

    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return CheckResult(
        check_type=check_type,
        cmd_args=args,
        file_path=file_path,
        stdout=ensure_decoded(stdout),
        stderr=ensure_decoded(stderr),
        returncode=process.returncode)


def check_python_code() -> bool:
    start_time = time.time()
    input_file_paths = (
        glob.glob(os.path.join(YB_THIRDPARTY_DIR, 'build_definitions', '*.py')) +
        glob.glob(os.path.join(YB_THIRDPARTY_DIR, '*.py'))
    )

    for dirpath, dirnames, filenames in os.walk(
            os.path.join(YB_THIRDPARTY_DIR, 'python')):
        for file_name in filenames:
            if file_name.endswith('.py'):
                input_file_paths.append(os.path.join(dirpath, file_name))

    os.environ['MYPYPATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    reporter = Reporter(line_width=80)
    checks_by_dir: Dict[str, int] = {}
    checks_by_type: Dict[str, int] = {}
    checks_by_result: Dict[str, int] = {}

    success = True

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_to_check_input = {
            executor.submit(check_file, file_path, check_type): (file_path, check_type)
            for file_path in input_file_paths
            for check_type in CHECK_TYPES if check_type != 'import'
        }
        for future in concurrent.futures.as_completed(future_to_check_input):
            file_path, check_type = future_to_check_input[future]
            try:
                check_result = future.result()
            except Exception as exc:
                print("Check '%s' for %s generated an exception: %s" % (check_type, file_path, exc))
                success = False
            else:
                reporter.print_check_result(check_result)
                if check_result.cmd_args:
                    rel_dir = os.path.dirname(rel_to_repo_root(file_path)) or 'root'
                    increment_counter(checks_by_dir, rel_dir)
                    increment_counter(checks_by_type, check_result.check_type)
                if check_result.returncode == 0:
                    increment_counter(checks_by_result, 'success')
                else:
                    increment_counter(checks_by_result, 'failure')
                    success = False

    print_stats("Checks by directory (relative to repo root)", checks_by_dir)
    print_stats("Checks by type", checks_by_type)
    print_stats("Checks by result", checks_by_result)
    print("Elapsed time: %.1f seconds" % (time.time() - start_time))
    print()
    if success:
        print("All checks are successful")
    else:
        print("Some checks failed")
    print()
    return success


if __name__ == '__main__':
    if check_python_code():
        sys.exit(0)
    sys.exit(1)
