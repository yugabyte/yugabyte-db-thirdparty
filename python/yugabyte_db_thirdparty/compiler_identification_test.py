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
import unittest

from yugabyte_db_thirdparty.compiler_identification import CompilerIdentification
from yugabyte_db_thirdparty.util import read_file

TEST_DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'test_input', 'compiler_identification')


class TestCompilerIdentification(unittest.TestCase):
    def run_one_test(
            self,
            input_file_name: str,
            expected_family: str,
            expected_version: str) -> None:
        compiler_identification = CompilerIdentification(
            read_file(os.path.join(TEST_DATA_DIR, input_file_name)))
        self.assertEqual(expected_family, compiler_identification.family)
        self.assertEqual(expected_version, compiler_identification.version)

    def test_clang10_apple(self) -> None:
        self.run_one_test('clang-10.0.1-macos.txt', 'clang', '10.0.1')

    def test_clang10_centos7_yb_built(self) -> None:
        self.run_one_test('clang-10.0.1-centos7-yb-built.txt', 'clang', '10.0.1')

    def test_clang11_centos7_yb_built(self) -> None:
        self.run_one_test('clang-11.0.0-centos7-yb-built.txt', 'clang', '11.0.0')

    def test_gcc7_ubuntu(self) -> None:
        self.run_one_test('gcc-7.5.0-ubuntu.txt', 'gcc', '7.5.0')

    def test_gcc8_ubuntu(self) -> None:
        self.run_one_test('gcc-8.4.0-ubuntu.txt', 'gcc', '8.4.0')
