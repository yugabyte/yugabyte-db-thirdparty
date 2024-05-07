#!/usr/bin/env bash

set -euo pipefail

readonly CI_BUILD_TYPES_KEYWORD="CI build types:"
GIT_HEAD_COMMIT_MESSAGE=$( git log --format=%B -n 1 --no-merges )
readonly GIT_HEAD_COMMIT_MESSAGE

echo "Git HEAD commit message: $GIT_HEAD_COMMIT_MESSAGE"

build_type=$YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX
echo "Build type: $build_type"

# A quick way to filter build types in the commit message.
should_build=true
if [[ $GIT_HEAD_COMMIT_MESSAGE == *"$CI_BUILD_TYPES_KEYWORD"* ]]; then

  # The commit message includes a line such as the following:
  #
  # CI build types: centos7-x86_64-clang15, centos7-x86_64-clang15-full-lto, centos7-x86_64-clang16,
  # centos7-x86_64-clang16-full-lto

  # This syntax in the commit message allows us to only build a subset of build types for a
  # particular commit / pull request. The build jobs are still started for all build types, but they
  # finish very quickly if the build type is filtered out.

  # Extract build types from the commit message
  build_types_str=$(
    grep -oP "(?<=$CI_BUILD_TYPES_KEYWORD: ).*" <<< "$GIT_HEAD_COMMIT_MESSAGE"
  )

  # Convert the build types to an array, trimming spaces manually
  IFS=',' read -r -a build_type_patterns_array <<< "$build_types_str"
  build_type_patterns_array=()
  should_build=false
  for build_type_pattern in "${build_type_patterns_array[@]}"; do
    # Remove leading/trailing whitespace.
    build_type_pattern=${build_type_pattern#"${build_type_pattern%%[![:space:]]*}"}
    build_type_pattern=${build_type_pattern%"${build_type_pattern##*[![:space:]]}"}
    if [[ $build_type_pattern =~ ^[a-zA-Z0-9*-_]$ ]]; then
      if [[ "$build_type" == *$build_type_pattern* ]]; then
        echo >&2 "Build type '$$build_type' matched pattern" \
                 "'$build_type_pattern', proceeding with the build."
        should_build=true
        break
      fi
    else
      echo >&2 "Warning: skipping invalid build type pattern '$build_type_pattern'. It must" \
               "consist of letters, numbers, dashes, underscores, and asterisks."
    fi
  done
fi

if [[ $should_build == "true" ]]; then
  if [[ $OSTYPE == darwin* ]]; then
    ./.github/workflows/macos_build.sh
  else
    ./.github/workflows/linux_build.sh
  fi
else
  echo "Build type $build_type filtered out by the" \
       "'$CI_BUILD_TYPES_KEYWORD' commit message filter."
fi
