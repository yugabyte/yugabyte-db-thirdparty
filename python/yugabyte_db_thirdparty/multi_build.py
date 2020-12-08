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
import shlex
import fnmatch
import docker  # type: ignore

from typing import List, Dict, Optional, Any
from yugabyte_db_thirdparty.util import (
    mkdir_if_missing,
    PushDir,
    YB_THIRDPARTY_DIR,
    log_and_run_cmd,
)
from yugabyte_db_thirdparty.string_util import shlex_join
from yugabyte_db_thirdparty.custom_logging import log, convert_log_args_to_message, PrefixLogger
from yugabyte_db_thirdparty.remote_build import copy_code_to


CIRCLECI_CONFIG_PATH = os.path.join(YB_THIRDPARTY_DIR, '.circleci', 'config.yml')

CENTOS7_DOCKER_IMAGE = 'yugabyteci/yb_build_infra_centos7:v2020-10-17T18_09_58'


class BuildResult:
    def __init__(self) -> None:
        pass


class MultiBuildCommonConf:
    def __init__(self) -> None:
        self.timestamp_str = datetime.datetime.now().strftime('%Y-%m-%dT%H_%M_%S')
        self.dir_of_all_runs = os.path.join(
            os.path.expanduser('~'), 'yugabyte-db-thirdparty-multi-build')
        self.root_run_dir = os.path.join(self.dir_of_all_runs, self.timestamp_str)
        self.checkout_dir = os.path.join(self.root_run_dir, 'code', 'yugabyte-db-thirdparty')


class BuildConfiguration(PrefixLogger):
    # Name of this configuration.
    name: str

    common_conf: MultiBuildCommonConf

    docker_image: str

    build_thirdparty_args: str

    def get_log_prefix(self) -> str:
        return "[%s] " % self.name

    def __init__(
            self,
            common_conf: MultiBuildCommonConf,
            name: str,
            docker_image: str,
            archive_name_suffix: str,
            build_thirdparty_args: str) -> None:
        self.common_conf = common_conf
        self.name = name
        self.docker_image = docker_image
        self.archive_name_suffix = archive_name_suffix
        self.build_thirdparty_args = build_thirdparty_args

    def prepare(self) -> None:
        self.conf_run_dir = os.path.join(self.common_conf.root_run_dir, self.name)
        self.output_file_path = os.path.join(self.conf_run_dir, 'output.log')
        mkdir_if_missing(self.conf_run_dir)

    def build(self) -> BuildResult:
        with PushDir(self.conf_run_dir):
            home_dir_in_container = '/home/yugabyteci'
            pip_cache_dir_in_container = os.path.join(home_dir_in_container, '.cache', 'pip')
            readonly_checkout_in_container = '/opt/yb-build/readonly-code/yugabyte-db-thirdparty'
            rw_checkout_in_container = '/opt/yb-build/thirdparty/checkout'
            sudo_cmd = 'sudo -u yugabyteci '
            # TODO: create a shell script in the checkout directory outside container with all the
            # right settings so we can rerun it manually easily if needed.
            bash_script = '; '.join([
                f"set -euxo pipefail",
                'mkdir -p /root/.cache/pip',
                'chmod a+rX /root',
                'chmod a+rX /root/.cache',
                'chmod -R a+rX /root/.cache/pip',
                # Here, before we switch user to yugabyteci, we can do things as root if needed.
                'sudo -u yugabyteci /bin/bash -c ' + shlex.quote('; '.join([
                    'set -euxo pipefail',
                    f'mkdir -p {pip_cache_dir_in_container}',
                    f'export PIP_DOWNLOAD_CACHE={pip_cache_dir_in_container}',
                    f"export YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX={self.archive_name_suffix}",
                    f"export YB_BUILD_THIRDPARTY_ARGS='{self.build_thirdparty_args}'",
                    f"cp -R {readonly_checkout_in_container} {rw_checkout_in_container}",
                    f"cd {rw_checkout_in_container}",
                    "./build_and_release.sh"
                ]))
            ])
            container_name = f'{self.name}-{self.common_conf.timestamp_str}'
            docker_run_cmd_args = [
                'docker',
                'run',
                '--name',
                container_name,
                '--cap-add=SYS_PTRACE',
                '--mount',
                ','.join([
                    'type=bind',
                    f'source={self.common_conf.checkout_dir}',
                    f'target={readonly_checkout_in_container}',
                    'readonly',
                ]),
                self.docker_image,
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
    common_conf: MultiBuildCommonConf

    def __init__(self, conf_name_pattern: str) -> None:
        self.common_conf = MultiBuildCommonConf()
        latest_link_path = os.path.join(self.common_conf.dir_of_all_runs, 'latest')

        mkdir_if_missing(os.path.dirname(self.common_conf.checkout_dir))
        if os.path.exists(latest_link_path):
            os.remove(latest_link_path)
        os.symlink(os.path.basename(self.common_conf.root_run_dir), latest_link_path)
        copy_code_to(self.common_conf.checkout_dir)

        with open(CIRCLECI_CONFIG_PATH) as circleci_conf_file:
            circleci_conf = yaml.load(circleci_conf_file, Loader=yaml.SafeLoader)

        self.configurations = []

        for circleci_job in circleci_conf['workflows']['build-release']['jobs']:
            build_params = circleci_job['build']
            conf = BuildConfiguration(
                common_conf=self.common_conf,
                name=build_params['name'],
                docker_image=build_params['docker_image'],
                archive_name_suffix=build_params['archive_name_suffix'],
                build_thirdparty_args=build_params.get('build_thirdparty_args', ''))
            if not conf_name_pattern:
                self.configurations.append(conf)
                continue
            if not fnmatch.fnmatch(conf.name, conf_name_pattern):
                log("Skipping configuration '%s' (does not match pattern %s)",
                    conf.name, conf_name_pattern)
                continue
            self.configurations.append(conf)

        for conf in self.configurations:
            log("Will build configuration: %s", conf.name)

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
                        # TODO: print the traceback
