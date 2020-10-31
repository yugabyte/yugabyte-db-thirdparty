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


class CompilerIdentification:
    """
    Given a compiler, determines its version, its installation directory, and other information that
    might influence how we should build the code.
    """
    compiler_family: str
    compiler_version: str

    def __init__(
            self,
            compiler_version_str: str):
        compiler_version_str = compiler_version_str.strip()
        m = LLVM_VERSION_RE.search(compiler_version_str)
        if m:
            self.compiler_family = 'clang'
            self.compiler_version = m.group(1)
            return
