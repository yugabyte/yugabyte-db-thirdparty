#!/usr/bin/env bash

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

log() {
  echo >&2 "[$( date +%Y-%m-%dT%H:%M:%S )] $*"
}

fatal() {
  log "$@"
  exit 1
}

compute_sha256sum() {
  sha256_sum=$( (
    if [[ $OSTYPE =~ darwin ]]; then
      local portable_arg=""
      if shasum --help | grep -qE '[-][-]portable'; then
        portable_arg="--portable"
      fi
      shasum $portable_arg --algorithm 256 "$@"
    else
      sha256sum "$@"
    fi
  ) | awk '{print $1}' )
  if [[ ! $sha256_sum =~ ^[0-9a-f]{64} ]]; then
    log "Got an incorrect SHA256 sum: $sha256_sum. Expected 64 hex digits."
  fi
}

detect_os() {
  os_name=""

  # shellcheck disable=SC2034
  is_ubuntu=false
  # shellcheck disable=SC2034
  is_centos=false
  # shellcheck disable=SC2034
  is_mac=false

  if [[ $OSTYPE == linux* ]]; then
    if grep -q Ubuntu /etc/issue; then
      # shellcheck disable=SC2034
      is_ubuntu=true
      os_name="ubuntu"
    fi

    if [[ -f /etc/os-release ]] && grep -q CentOS /etc/os-release; then
      # shellcheck disable=SC2034
      is_centos=true
      os_name="centos"
    fi
  elif [[ $OSTYPE == darwin* ]]; then
    # shellcheck disable=SC2034
    is_mac=true
    os_name="macos"
  fi

  if [[ -z $os_name ]]; then
    fatal "Failed to determine OS name. OSTYPE: $OSTYPE" >&2
  fi
}

check_bash_scripts() {
  if ! command -v shellcheck >/dev/null; then
    return
  fi

  cd "$YB_THIRDPARTY_DIR"
  local bash_scripts
  # Use the fact that there are no spaces in the shell script names in this repository.
  # shellcheck disable=SC2207
  bash_scripts=( $( find . -mindepth 1 -maxdepth 1 -type f -name "*.sh" ) )

  local shell_script
  for shell_script in "${bash_scripts[@]}"; do
    shellcheck -x "$shell_script"
  done
}


activate_virtualenv() {
  if [[ ! -d $YB_THIRDPARTY_DIR/venv ]]; then
    python3 -m venv "$YB_THIRDPARTY_DIR/venv"
  fi
  set +u
  # shellcheck disable=SC1090
  . "$YB_THIRDPARTY_DIR/venv/bin/activate"
  set -u
  ( set -x; cd "$YB_THIRDPARTY_DIR" && pip3 install -r requirements.txt )
}

detect_os

# We ignore the previously set YB_THIRDPARTY_DIR value, because if we are executing Bash scripts
# within this third-party directory, we most likely want to work in this exact directory.
YB_THIRDPARTY_DIR=$( cd "${BASH_SOURCE[0]%/*}" && pwd )
export YB_THIRDPARTY_DIR