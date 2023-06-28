#!/usr/bin/env bash

set -euo pipefail

readonly CI_BUILD_TYPES_KEYWORD="CI build types:"
GIT_HEAD_COMMIT_MESSAGE=$( git log --format=%B -n 1 --no-merges )

echo "Git HEAD commit message: $GIT_HEAD_COMMIT_MESSAGE"

# A quick way to filter build types in the commit message.
if [[ $GIT_HEAD_COMMIT_MESSAGE != *"$CI_BUILD_TYPES_KEYWORD"* ||
      $GIT_HEAD_COMMIT_MESSAGE == \
          *"$CI_BUILD_TYPES_KEYWORD"*"$YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX"* ]]; then
  echo "Git HEAD commit message does not specify a build type filter, or the filter" \
       "matches build type: $YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX"
  if [[ $OSTYPE == darwin* ]]; then
    ./.github/workflows/macos_build.sh
  else
    ./.github/workflows/linux_build.sh
  fi
else
  echo "Build type $YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX filtered out by the" \
       "'$CI_BUILD_TYPES_KEYWORD' commit message filter."
fi
