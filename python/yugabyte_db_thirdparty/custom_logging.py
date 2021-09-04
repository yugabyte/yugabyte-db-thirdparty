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
import logging

from yugabyte_db_thirdparty.string_util import shlex_join
from typing import List, Any, NoReturn, Pattern, Optional


g_logging_configured = False


YELLOW_COLOR = "\033[0;33m"
RED_COLOR = "\033[0;31m"
CYAN_COLOR = "\033[0;36m"
NO_COLOR = "\033[0m"
SEPARATOR = "-" * 80


# Based on http://bit.ly/python_terminal_color_detection (code from Django).
def _terminal_supports_colors() -> bool:
    """
    Returns True if the running system's terminal supports color, and False
    otherwise.
    """
    plat = sys.platform
    supported_platform = plat != 'Pocket PC' and (plat != 'win32' or
                                                  'ANSICON' in os.environ)
    # isatty is not always implemented, #6223.
    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    return supported_platform and is_a_tty


terminal_supports_colors = _terminal_supports_colors()


def convert_log_args_to_message(*args: Any) -> str:
    n_args = len(args)
    if n_args == 0:
        message = ""
    elif n_args == 1:
        message = args[0]
    else:
        message = args[0] % args[1:]
    return message


class FatalError(Exception):
    pass


def fatal(*args: Any) -> NoReturn:
    log(*args)
    traceback.print_stack()
    msg = convert_log_args_to_message(*args)
    # Do not use sys.exit here because that would skip upstream exception handling.
    raise FatalError(msg)


def log(*args: Any) -> None:
    if not g_logging_configured:
        raise RuntimeError("log() called before logging is configured")
    logging.info(*args)


def colored_log(color: str, *args: Any) -> None:
    if terminal_supports_colors:
        sys.stderr.write(color + convert_log_args_to_message(*args) + NO_COLOR + "\n")
    else:
        log(*args)


def print_line_with_colored_prefix(prefix: str, line: str) -> None:
    log("%s[%s] %s%s", CYAN_COLOR, prefix, NO_COLOR, line.rstrip())


def log_output(
        prefix: str,
        args: List[Any],
        disallowed_pattern: Optional[Pattern] = None) -> None:
    cmd_str = shlex_join(args)
    try:
        print_line_with_colored_prefix(
            prefix, "Running command: {} (current directory: {})".format(cmd_str, os.getcwd()))
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert process.stdout is not None
        for line in process.stdout:
            if disallowed_pattern and disallowed_pattern.search(line):
                raise RuntimeError(
                    "Output line from command [[ {} ]] contains a disallowed pattern: {}".format(
                        cmd_str, disallowed_pattern))

            print_line_with_colored_prefix(prefix, line.decode('utf-8'))

        process.stdout.close()
        exit_code = process.wait()
        if exit_code:
            # We do not use fatal() here because that would skip upstream exception handling.
            raise RuntimeError("Execution failed with code: {}".format(exit_code))
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


class PrefixLogger:
    def log_with_prefix(self, *args: Any) -> None:
        log('%s%s', self.get_log_prefix(), convert_log_args_to_message(*args))

    def get_log_prefix(self) -> str:
        raise NotImplementedError()


def configure_logging() -> None:
    global g_logging_configured
    if g_logging_configured:
        return
    g_logging_configured = True
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
