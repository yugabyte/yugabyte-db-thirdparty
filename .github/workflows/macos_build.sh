#!/usr/bin/env bash

set -euo pipefail

brew install autoconf automake pkg-config shellcheck hub
dirs=( /opt/yb-build/{thirdparty,brew,tmp} )
sudo mkdir -p "${dirs[@]}"
sudo chmod 777 "${dirs[@]}"

export PYTHON="python3.11"
./build_and_release.sh
