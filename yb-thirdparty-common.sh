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

activate_virtualenv() {
  if [[ ! -d $YB_THIRDPARTY_DIR/venv ]]; then
    python3 -m venv "$YB_THIRDPARTY_DIR/venv"
  fi
  set +u
  # shellcheck disable=SC1090
  . "$YB_THIRDPARTY_DIR/venv/bin/activate"
  set -u
  (
    set -x
    cd "$YB_THIRDPARTY_DIR"
    pip3 install --quiet -r requirements_frozen.txt
  )
}

# Re-executes the current script with the correct macOS architecture.
ensure_correct_mac_architecture() {
  if [[ $OSTYPE != darwin* ]]; then
    return
  fi
  if [[ -z ${YB_TARGET_ARCH:-} ]]; then
    local uname_p_output
    uname_p_output=$( uname -p )
    if [[ $uname_p_output == arm || $uname_p_output == arm64 ]]; then
      YB_TARGET_ARCH="arm64"
    elif [[ $uname_p_output == i386 || $uname_p_output == x86_64 ]]; then
      YB_TARGET_ARCH="x86_64"
    else
      fatal "Failed to determine target architecture on macOS from the output of 'uname -p':" \
            "$uname_p_output"
    fi
  fi
  if [[ $YB_TARGET_ARCH != "x86_64" && $YB_TARGET_ARCH != "arm64" ]]; then
    fatal "Invalid value of YB_TARGET_ARCH on macOS (expected x86_64 or arm64): $YB_TARGET_ARCH"
  fi
  export YB_TARGET_ARCH
  local actual_arch
  actual_arch=$(arch)
  if [[ $actual_arch == "i386" ]]; then
    actual_arch="x86_64"
  elif [[ $actual_arch != "arm64" && $actual_arch != "x86_64" ]]; then
    fatal "Unexpected output from arch: $actual_arch"
  fi
  if [[ $actual_arch != "$YB_TARGET_ARCH" ]]; then
    echo "Switching architecture to $YB_TARGET_ARCH"
    set -x
    exec arch "-$YB_TARGET_ARCH" "$0" "$@"
  fi
}

# We ignore the previously set YB_THIRDPARTY_DIR value, because if we are executing Bash scripts
# within this third-party directory, we most likely want to work in this exact directory.
YB_THIRDPARTY_DIR=$( cd "${BASH_SOURCE[0]%/*}" && pwd )

PYTHONPATH=${PYTHONPATH:-}
if [[ -n $PYTHONPATH ]]; then
  PYTHONPATH=:$PYTHONPATH
fi

# Eventually most Python scripts should move to the python directory, but right now we add both
# the "python" directory and the thirdparty root directory to PYTHONPATH.
PYTHONPATH=$YB_THIRDPARTY_DIR/python$PYTHONPATH

export PYTHONPATH
export YB_THIRDPARTY_DIR
