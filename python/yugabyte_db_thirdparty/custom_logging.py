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

import os
import sys
import subprocess
import traceback
from typing import List, Any, NoReturn


YELLOW_COLOR = "\033[0;33m"
RED_COLOR = "\033[0;31m"
CYAN_COLOR = "\033[0;36m"
NO_COLOR = "\033[0m"
SEPARATOR = "-" * 80


def _args_to_message(*args: Any) -> str:
    n_args = len(args)
    if n_args == 0:
        message = ""
    elif n_args == 1:
        message = args[0]
    else:
        message = args[0] % args[1:]
    return message


def fatal(*args: Any) -> NoReturn:
    log(*args)
    traceback.print_stack()
    sys.exit(1)


def log(*args: Any) -> None:
    sys.stderr.write(_args_to_message(*args) + "\n")


def colored_log(color: str, *args: Any) -> None:
    sys.stderr.write(color + _args_to_message(*args) + NO_COLOR + "\n")


def print_line_with_colored_prefix(prefix: str, line: str) -> None:
    log("%s[%s] %s%s", CYAN_COLOR, prefix, NO_COLOR, line.rstrip())


def log_output(prefix: str, args: List[Any], log_cmd: bool = True) -> None:
    try:
        print_line_with_colored_prefix(
            prefix, "Running command: {} (current directory: {})".format(
                args, os.getcwd()))
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert process.stdout is not None
        for line in process.stdout:
            print_line_with_colored_prefix(prefix, line.decode('utf-8'))

        process.stdout.close()
        exit_code = process.wait()
        if exit_code:
            fatal("Execution failed with code: {}".format(exit_code))
    except OSError as err:
        log("Error when trying to execute command: " + str(args))
        log("PATH is: %s", os.getenv("PATH"))
        raise


def log_separator() -> None:
    log("")
    log(SEPARATOR)
    log("")


def heading(title: str) -> None:
    log("")
    log(SEPARATOR)
    log(title)
    log(SEPARATOR)
    log("")
