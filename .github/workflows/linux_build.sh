#!/usr/bin/env bash

set -euo pipefail

df -H .
checkout_dir=$PWD
export YB_SKIP_UPLOAD=${SKIP_UPLOAD:-}
echo "Building in directory: $checkout_dir"
docker run -t \
  --cap-add=SYS_PTRACE \
  -e GITHUB_TOKEN \
  -e SNYK_TOKEN \
  -e YB_BUILD_THIRDPARTY_ARGS \
  -e YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX \
  -e YB_SKIP_UPLOAD \
  "--mount=type=bind,src=$checkout_dir,dst=/opt/yb-build/thirdparty/checkout" \
  "$YB_DOCKER_IMAGE" \
  bash -c '
    set -euo pipefail
    cd /opt/yb-build/thirdparty/checkout
    # To avoid the "unsafe repository owned by someone else" git error:
    if ! chown -R "$(whoami)" "$PWD"; then
      set +e
      ls -l /opt
      ls -l /opt/yb-build
      ls -l /opt/yb-build/thirdparty
      ls -l /opt/yb-build/thirdparty/checkout
      set -e
      exit 1
    done
    ./build_and_release.sh
  '
