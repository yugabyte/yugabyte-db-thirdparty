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
      shasum --portable --algorithm 256 "$@"
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

  is_ubuntu=false
  is_centos=false
  is_mac=false

  if [[ $OSTYPE == linux* ]]; then
    if grep -q Ubuntu /etc/issue; then
      is_ubuntu=true
      os_name="ubuntu"
    fi

    if [[ -f /etc/os-release ]] && grep -q CentOS /etc/os-release; then
      is_centos=true
      os_name="centos"
    fi
  elif [[ $OSTYPE == darwin* ]]; then
    is_mac=true
    os_name="macos"
  fi

  if [[ -z $os_name ]]; then
    fatal "Failed to determine OS name. OSTYPE: $OSTYPE" >&2
  fi
}

detect_os
