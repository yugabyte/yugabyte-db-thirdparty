#!/usr/bin/env bash
#
# Copyright (c) YugaByte, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
# in compliance with the License.  You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied.  See the License for the specific language governing permissions and limitations
# under the License.
#

set -euo pipefail

# shellcheck source=./yb-thirdparty-common.sh
. "${BASH_SOURCE[0]%/*}/yb-thirdparty-common.sh"

# This may re-execute the current script using the "arch" command based on YB_TARGET_ARCH.
ensure_correct_mac_architecture "$@"

build_thirdparty_args=( "$@" )
toolchain=""
# Do some lightweight parsing of the arguments to find what we need for the log file name.
# TODO: redirect log to file in Python itself, so we don't have to do this parsing here.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --toolchain=*)
      toolchain=${1#--toolchain=}
    ;;
    --toolchain)
      toolchain=$2
      shift
    ;;
  esac
  shift
done
activate_virtualenv

log_dir=$HOME/logs
mkdir -p "${log_dir}"
log_file_name=build_thirdparty
latest_log_links=( "build_thirdparty_latest.log" )
if [[ -n ${toolchain} ]]; then
  log_file_name+=_${toolchain}
  latest_log_links=( "build_thirdparty_latest_${toolchain}.log" )
fi
log_file_name+=_$( date +%Y-%m-%dT%H_%M_%S ).log
log_path=${log_dir}/${log_file_name}
(
  cd "${log_dir}"
  for link_name in "${latest_log_links[@]}"; do
    ln -sf "${log_file_name}" "${link_name}"
  done
)
link_path_list_str=""
for link_name in "${latest_log_links[@]}"; do
  if [[ -n ${link_path_list_str} ]]; then
    link_path_list_str+=", "
  fi
  link_path_list_str+=${link_name}
done

echo
echo "Logging to ${log_path} (linked to ${link_path_list_str})"
echo

cmd=( python3 "${YB_THIRDPARTY_DIR}/python/yugabyte_db_thirdparty/yb_build_thirdparty_main.py" )
if [[ ${#build_thirdparty_args[@]} -gt 0 ]]; then
  cmd+=( "${build_thirdparty_args[@]}" )
fi

# Cannot use |& redirection of both stdout and stderr due to the need to support Bash 3.
(
  set -x
  "${cmd[@]}"
) 2>&1 | tee "${log_path}"

echo
echo "Log saved to ${log_path}"
echo
