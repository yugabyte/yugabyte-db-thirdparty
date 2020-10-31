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


import concurrent.futures

from typing import List, Dict, Optional


CENTOS7_DOCKER_IMAGE = 'yugabyteci/yb_build_infra_centos7:v2020-10-17T18_09_58'


class BuildResult:
    def __init__(self) -> None:
        pass


class BuildConfiguration:
    def __init__(self, name: str, docker_image: str, args: List[str]) -> None:
        self.name = name

    def build(self) -> BuildResult:
        return BuildResult()


def build_configuration(configuration: BuildConfiguration) -> BuildResult:
    return configuration.build()


class MultiBuilder:
    configurations: List[BuildConfiguration]

    def __init__(self) -> None:
        self.configurations = [
            BuildConfiguration(
                name='centos7-linuxbrew',
                docker_image=CENTOS7_DOCKER_IMAGE,
                args=[]
            ),
        ]

    def build_all(self) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            for configuration in self.configurations:
                future_to_configuration = {
                    executor.submit(build_configuration, configuration): configuration
                    for configuration in self.configurations
                }
                for future in concurrent.futures.as_completed(future_to_configuration):
                    pass


def main() -> None:
    multi_builder = MultiBuilder()
    multi_builder.build_all()


if __name__ == '__main__':
    main()
