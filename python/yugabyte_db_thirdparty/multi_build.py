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
import concurrent.futures
import datetime
import yaml
import shutil
import subprocess
import time

from typing import List, Dict, Optional, Any
from yugabyte_db_thirdparty.util import (
    mkdir_if_missing,
    PushDir,
    log_and_run_cmd,
    YB_THIRDPARTY_DIR,
    shlex_join,
)
from yugabyte_db_thirdparty.custom_logging import log, convert_log_args_to_message, PrefixLogger
from yugabyte_db_thirdparty.remote_build import copy_code_to


CIRCLECI_CONFIG_PATH = os.path.join(YB_THIRDPARTY_DIR, '.circleci', 'config.yml')

CENTOS7_DOCKER_IMAGE = 'yugabyteci/yb_build_infra_centos7:v2020-10-17T18_09_58'


class BuildResult:
    def __init__(self) -> None:
        pass


class BuildConfiguration(PrefixLogger):
    # Name of this configuration.
    name: str

    # Directory for all configurations. This is the same in all BuildConfiguration objects.
    root_run_dir: str

    # Directory for this particular configuartion. This is a subdirectory of root_run_dir based
    # on the name.
    conf_run_dir: str

    # Code checkout directory. One for all configuration builds.
    code_dir: str

    docker_image: str

    build_thirdparty_args: str

    def get_log_prefix(self) -> str:
        return "[%s] " % self.name

    def __init__(
            self,
            root_run_dir: str,
            code_dir: str,
            name: str,
            docker_image: str,
            archive_name_suffix: str,
            build_thirdparty_args: str) -> None:
        self.root_run_dir = root_run_dir
        self.code_dir = code_dir
        self.name = name
        self.docker_image = docker_image
        self.archive_name_suffix = archive_name_suffix
        self.build_thirdparty_args = build_thirdparty_args

    def prepare(self) -> None:
        self.conf_run_dir = os.path.join(self.root_run_dir, self.name)
        self.output_file_path = os.path.join(self.conf_run_dir, 'output.log')
        mkdir_if_missing(self.conf_run_dir)

    def build(self) -> BuildResult:
        with PushDir(self.conf_run_dir):
            code_dir_in_container_parent = '/home/yugabyteci/code'
            code_dir_in_container = os.path.join(
                code_dir_in_container_parent, 'yugabyte-db-thirdparty')
            code_dir_in_container_readonly = '/readonly-mount/yugabyte-db-thirdparty'
            bash_script = '; '.join([
                f"set -euxo pipefail",
                f"export PATH=/usr/local/bin:$PATH",
                f"mkdir -p {code_dir_in_container_parent}",
                f"cp -R {code_dir_in_container_readonly} {code_dir_in_container}",
                f"export YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX={self.archive_name_suffix}",
                f"export YB_BUILD_THIRDPARTY_ARGS='{self.build_thirdparty_args}'",
                "./build_and_release.sh"
            ])
            docker_run_cmd_args = [
                'docker',
                'run',
                '--cap-add=SYS_PTRACE',
                '--mount',
                ','.join([
                    'type=bind',
                    f'source={self.code_dir}',
                    f'target={code_dir_in_container_readonly}',
                    'readonly',
                ]),
                self.docker_image,
                'sudo',
                '-u',
                'yugabyteci',
                'bash',
                '-c',
                bash_script
            ]
            self.log_with_prefix("Running command: %s", shlex_join(docker_run_cmd_args))
            self.log_with_prefix("Logging to: %s", self.output_file_path)
            start_time_sec = time.time()
            with open(self.output_file_path, 'wb') as output_file:
                docker_run_process = subprocess.Popen(
                    docker_run_cmd_args, stdout=output_file, stderr=subprocess.STDOUT)
                docker_run_process.wait()
                elapsed_time_sec = time.time() - start_time_sec
            self.log_with_prefix(
                "Return code: %d, elapsed time: %.1f sec",
                docker_run_process.returncode,
                elapsed_time_sec)

        return BuildResult()


def build_configuration(configuration: BuildConfiguration) -> BuildResult:
    return configuration.build()


class MultiBuilder:
    configurations: List[BuildConfiguration]
    common_timestamp_str: str
    root_run_dir: str

    def __init__(self) -> None:
        self.common_timestamp_str = datetime.datetime.now().strftime('%Y-%m-%dT%H_%M_%S')
        dir_of_all_runs = os.path.join(
            os.path.expanduser('~'), 'yugabyte-db-thirdparty-multi-build')
        self.root_run_dir = os.path.join(dir_of_all_runs, self.common_timestamp_str)
        latest_link = os.path.join(dir_of_all_runs, 'latest')
        self.code_dir = os.path.join(self.root_run_dir, 'code', 'yugabyte-db-thirdparty')
        mkdir_if_missing(os.path.dirname(self.code_dir))
        if os.path.exists(latest_link):
            os.remove(latest_link)
        os.symlink(os.path.basename(self.root_run_dir), latest_link)
        copy_code_to(self.code_dir)

        with open(CIRCLECI_CONFIG_PATH) as circleci_conf_file:
            circleci_conf = yaml.load(circleci_conf_file, Loader=yaml.SafeLoader)

        self.configurations = []

        for circleci_job in circleci_conf['workflows']['build-release']['jobs']:
            build_params = circleci_job['build']
            self.configurations.append(
                BuildConfiguration(
                    root_run_dir=self.root_run_dir,
                    code_dir=self.code_dir,
                    name=build_params['name'],
                    docker_image=build_params['docker_image'],
                    archive_name_suffix=build_params['archive_name_suffix'],
                    build_thirdparty_args=build_params.get(
                        'build_thirdparty_args', '')))

    def build(self) -> None:
        for configuration in self.configurations:
            configuration.prepare()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            for configuration in self.configurations:
                future_to_configuration = {
                    executor.submit(build_configuration, configuration): configuration
                    for configuration in self.configurations
                }
                for future in concurrent.futures.as_completed(future_to_configuration):
                    try:
                        result = future.result()
                    except Exception as exc:
                        print("Build generated an exception: %s" % exc)
