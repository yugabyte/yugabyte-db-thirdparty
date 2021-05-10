#!/usr/bin/env bash

set -euo pipefail

brew install autoconf automake pkg-config shellcheck
dirs=( /opt/yb-build/{thirdparty,brew,tmp} )
sudo mkdir -p "${dirs[@]}"
sudo chmod 777 "${dirs[@]}"
./build_and_release.sh
