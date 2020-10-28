#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=./yb-thirdparty-common.sh
. "${BASH_SOURCE%/*}/yb-thirdparty-common.sh"

activate_virtualenv

python3 "$YB_THIRDPARTY_DIR/python/yugabyte_db_thirdparty/check_python_code.py" "$@"