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

import re
import shlex

from typing import Set, Optional, Any, List


LEADING_SPACES_RE = re.compile('^[ ]*')


def split_into_word_set(input_str: str) -> Set[str]:
    """
    >>> sorted(split_into_word_set('  foo    bar      foo  '))
    ['bar', 'foo']
    >>> sorted(split_into_word_set('  foo   \\n  hello    world \\n hello'))
    ['foo', 'hello', 'world']
    """

    items = [s.strip() for s in input_str.strip().split()]
    return set(item for item in items if item)


def indent_lines(s: Optional[str], num_spaces: int = 4) -> Optional[str]:
    """
    >>> indent_lines(None)
    >>> indent_lines('a\\nb')
    '    a\\n    b'
    >>> indent_lines('a\\nb\\n')
    '    a\\n    b\\n    '
    """
    if s is None:
        return s
    return "\n".join([
        ' ' * num_spaces + line for line in s.split("\n")
    ])


def normalize_cmd_arg(arg: Any) -> Any:
    # Auto-convert ints to strings, but don't convert anything else.
    if isinstance(arg, int):
        return str(arg)
    return arg


def normalize_cmd_args(args: List[Any]) -> List[str]:
    return [normalize_cmd_arg(arg) for arg in args]


def shlex_join(args: List[str], one_arg_per_line: bool = False) -> str:
    """
    We need this to be compatible with Python 3.7.
    """
    quoted_args = [shlex.quote(arg) for arg in args]
    if one_arg_per_line:
        return ' \\\n  '.join(quoted_args)
    return ' '.join(quoted_args)


def parse_bool(s: str) -> bool:
    return s.strip().lower() not in ['', '0', 'false', 'no']
