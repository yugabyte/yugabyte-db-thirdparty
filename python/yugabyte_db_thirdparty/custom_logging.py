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
import time
import string
import random

from yugabyte_db_thirdparty.string_util import shlex_join
from typing import List, Any, NoReturn, Pattern, Optional, Union


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


def format_line_with_colored_prefix(prefix: Optional[str], line: str, color: bool) -> str:
    line = line.rstrip()
    if prefix is None:
        return line
    if color:
        start_color = CYAN_COLOR
        end_color = NO_COLOR
    else:
        start_color = ''
        end_color = ''
    prefix = '%s[%s] %s' % (start_color, prefix, end_color)
    return prefix + line


class LogOutputException(Exception):
    def __init(self, message: str) -> None:
        super().__init__(message)


def log_output_internal(
        prefix: str,
        args: List[Any],
        disallowed_pattern: Optional[Pattern] = None,
        color: bool = True,
        hide_log_on_success: bool = False) -> None:
    cmd_str = shlex_join(args)
    output_file = None
    output_path = None
    if hide_log_on_success:
        output_path = '/tmp/yb-build-thirdparty-tmp-output-%s' % (
            ''.join(random.choice(string.ascii_lowercase) for i in range(32))
        )
        output_file = open(output_path, 'w')

    start_time_sec = time.time()

    exit_code: Union[str, int] = "<unknown>"

    def show_error_details() -> None:
        nonlocal output_file, output_path
        if output_file is None:
            return
        output_file.close()
        output_file = None
        assert output_path is not None
        with open(output_path) as output_file_for_reading:
            log("PATH is: %s", os.getenv("PATH"))
            log("Output from command: %s", cmd_str)
            for line_str in output_file_for_reading:
                log(line_str.rstrip())
            log("End of output from command: %s", cmd_str)
        os.remove(output_path)
        output_path = None

    try:
        log("Running command: %s (current directory: %s)", cmd_str, os.getcwd())
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert process.stdout is not None

        prev_line: Optional[bytes] = None
        for line in process.stdout:
            if disallowed_pattern and disallowed_pattern.search(line.decode('utf-8')):
                raise RuntimeError(
                    "Output line from command [[ {} ]] contains a disallowed pattern: {}".format(
                        cmd_str, disallowed_pattern))

            formatted_line = format_line_with_colored_prefix(
                # Do not print the prefix if the previous line ends with a line continuation
                # character.
                prefix=None if prev_line is not None and prev_line.endswith(b'\\\n') else prefix,
                line=line.decode('utf-8'),
                color=color)
            prev_line = line
            if output_file is None:
                log(formatted_line)
            else:
                output_file.write(formatted_line + '\n')

        process.stdout.close()
        exit_code = process.wait()
        if exit_code != 0:
            raise LogOutputException("Execution failed with code: {}".format(exit_code))
    except Exception:
        show_error_details()
        raise
    finally:
        elapsed_time_sec = time.time() - start_time_sec
        log("Command completed with exit code %s (took %.1f sec): %s",
            exit_code, elapsed_time_sec, cmd_str)


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
