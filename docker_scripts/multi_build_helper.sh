#!/usr/bin/env bash

# This script runs as root in Docker containers created by multi_build.py.

set -euo pipefail -x

chmod -R a+r /root/.cache/pip

sudo -u yugabyteci
