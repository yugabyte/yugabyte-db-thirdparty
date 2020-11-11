#!/usr/bin/env python3

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

import re

NUMERIC_VERSION_RE_STR = r'(\d+([.]\d+)*)'
LLVM_VERSION_RE = re.compile(r'LLVM version %s ' % NUMERIC_VERSION_RE_STR)
GCC_VERSION_RE = re.compile(r'gcc version %s ' % NUMERIC_VERSION_RE_STR)
CLANG_VERSION_RE = re.compile(r'clang version %s ' % NUMERIC_VERSION_RE_STR)


class CompilerIdentification:
    """
    Given a compiler, determines its version, its installation directory, and other information that
    might influence how we should build the code.
    """
    family: str
    version: str

    def __init__(
            self,
            version_str: str):
        version_str = version_str.strip()
        m = LLVM_VERSION_RE.search(version_str)
        if m:
            self.family = 'clang'
            self.version = m.group(1)
            return

        m = CLANG_VERSION_RE.search(version_str)
        if m:
            self.family = 'clang'
            self.version = m.group(1)
            return

        m = GCC_VERSION_RE.search(version_str)
        if m:
            self.family = 'gcc'
            self.version = m.group(1)
            return

        raise ValueError("Could not identify the compiler. '-v' output: %s" % version_str)
