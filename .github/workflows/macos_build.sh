#!/usr/bin/env bash

set -euo pipefail

brew install autoconf automake pkg-config shellcheck hub llvm@19
dirs=( /opt/yb-build/{thirdparty,brew,tmp} )
sudo mkdir -p "${dirs[@]}"
sudo chmod 777 "${dirs[@]}"

export PYTHON="python3.9"
./build_and_release.sh
