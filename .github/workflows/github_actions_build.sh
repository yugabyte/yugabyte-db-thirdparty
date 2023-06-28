#!/usr/bin/env bash

set -euo pipefail

GIT_HEAD_COMMIT_MESSAGE=$( git log --format=%B -n 1 --no-merges )
echo "GIT head commit message: $GIT_HEAD_COMMIT_MESSAGE"

# A quick way to filter build types in the commit message.
if [[ $GIT_HEAD_COMMIT_MESSAGE != *"CI build types:"* ||
      $GIT_HEAD_COMMIT_MESSAGE == \
          *"CI build types:"*"$YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX"* ]]; then
  echo "GitHub HEAD commit message does not specify a build type filter, or the filter" \
        "matches build type: $YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX"
  if false; then
    if [[ $OSTYPE == darwin* ]]; then
      ./.github/workflows/macos_build.sh
    else
      ./.github/workflows/linux_build.sh
    fi
  fi
else
  echo "Build type filtered out by commit message: $YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX"
fi
