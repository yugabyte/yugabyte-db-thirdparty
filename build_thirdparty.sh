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

check_bash_scripts

echo "YB_THIRDPARTY_DIR=$YB_THIRDPARTY_DIR"

if [[ ! -d $YB_THIRDPARTY_DIR/venv ]]; then
  python3 -m venv "$YB_THIRDPARTY_DIR/venv"
fi
set +u
# shellcheck disable=SC1090
. "$YB_THIRDPARTY_DIR/venv/bin/activate"
set -u
( set -x; cd "$YB_THIRDPARTY_DIR" && pip3 install -r requirements.txt )

echo "YB_LINUXBREW_DIR=${YB_LINUXBREW_DIR:-undefined}"
if [[ $OSTYPE == linux* && -n ${YB_LINUXBREW_DIR:-} ]]; then
  if [[ ! -d $YB_LINUXBREW_DIR ]]; then
    fatal "Directory specified by YB_LINUXBREW_DIR ('$YB_LINUXBREW_DIR') does not exist"
  fi
  export PATH=$YB_LINUXBREW_DIR/bin:$PATH
fi

echo "YB_CUSTOM_HOMEBREW_DIR=${YB_CUSTOM_HOMEBREW_DIR:-undefined}"

set -x

# YB_BUILD_THIRDPARTY_EXTRA_ARGS is an environment variable that could be set in the cloud-based
# CI provider.

# shellcheck disable=SC2086
python3 "$YB_THIRDPARTY_DIR/yb_build_thirdparty_main.py" "$@" ${YB_BUILD_THIRDPARTY_EXTRA_ARGS:-}
