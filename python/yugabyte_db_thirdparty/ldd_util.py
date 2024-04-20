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

from typing import List

from yugabyte_db_thirdparty.util import capture_all_output


LDD_ENV = {'LC_ALL': 'en_US.UTF-8'}


class LddResult:
    file_path: str
    output_lines: List[str]

    def __init__(self, file_path: str, output_lines: List[str]) -> None:
        self.file_path = file_path
        self.output_lines = output_lines

    def not_a_dynamic_executable(self) -> bool:
        """
        Checks if the output says that this is not a dynamic executable.
        """
        return any(['not a dynamic executable' in line for line in self.output_lines])


def run_ldd(file_path: str) -> LddResult:
    return LddResult(
        file_path=file_path,
        output_lines=capture_all_output(
            ['ldd', file_path],
            env=LDD_ENV,
            allowed_exit_codes={1}))