#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=./yb-thirdparty-common.sh
. "${BASH_SOURCE%/*}/yb-thirdparty-common.sh"

activate_virtualenv

set -x
codecheck --verbose
