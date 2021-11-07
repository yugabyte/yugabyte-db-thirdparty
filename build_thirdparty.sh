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

if [[ $OSTYPE == darwin* && $(arch) == "i386" && $(uname -a) == *ARM64* ]]; then
  exec arch -arm64 "$0" "$@"
  exit 1
fi

# shellcheck source=./yb-thirdparty-common.sh
. "${BASH_SOURCE[0]%/*}/yb-thirdparty-common.sh"

echo "YB_THIRDPARTY_DIR=$YB_THIRDPARTY_DIR"

activate_virtualenv

echo "YB_LINUXBREW_DIR=${YB_LINUXBREW_DIR:-undefined}"
if [[ $OSTYPE == linux* && -n ${YB_LINUXBREW_DIR:-} ]]; then
  if [[ ! -d $YB_LINUXBREW_DIR ]]; then
    fatal "Directory specified by YB_LINUXBREW_DIR ('$YB_LINUXBREW_DIR') does not exist"
  fi
  export PATH=$YB_LINUXBREW_DIR/bin:$PATH
fi

echo "YB_CUSTOM_HOMEBREW_DIR=${YB_CUSTOM_HOMEBREW_DIR:-undefined}"

set -x

# shellcheck disable=SC2086
python3 "$YB_THIRDPARTY_DIR/python/yugabyte_db_thirdparty/yb_build_thirdparty_main.py" "$@"
