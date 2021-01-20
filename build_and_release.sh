#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=./yb-thirdparty-common.sh
. "${BASH_SOURCE%/*}/yb-thirdparty-common.sh"

# -------------------------------------------------------------------------------------------------
# OS detection
# -------------------------------------------------------------------------------------------------

if ! "$is_mac"; then
  cat /proc/cpuinfo
fi

# -------------------------------------------------------------------------------------------------
# Display various settings
# -------------------------------------------------------------------------------------------------

# Current user
USER=$(whoami)
log "Current user: $USER"

# PATH
export PATH=/usr/local/bin:$PATH
log "PATH: $PATH"

YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX=${YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX:-}
log "YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX: ${YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX:-undefined}"

YB_BUILD_THIRDPARTY_ARGS=${YB_BUILD_THIRDPARTY_ARGS:-}
log "YB_BUILD_THIRDPARTY_ARGS: ${YB_BUILD_THIRDPARTY_ARGS:-undefined}"

YB_BUILD_THIRDPARTY_EXTRA_ARGS=${YB_BUILD_THIRDPARTY_EXTRA_ARGS:-}
log "YB_BUILD_THIRDPARTY_EXTRA_ARGS: ${YB_BUILD_THIRDPARTY_EXTRA_ARGS:-undefined}"

# -------------------------------------------------------------------------------------------------
# Installed tools
# -------------------------------------------------------------------------------------------------

echo "Bash version: $BASH_VERSION"

tools_to_show_versions=(
  cmake
  automake
  autoconf
  autoreconf
  pkg-config
)

if "$is_mac"; then
  tools_to_show_versions+=( shasum )
elif "$is_centos"; then
  tools_to_show_versions+=( sha256sum libtool )
else
  tools_to_show_versions+=( sha256sum )
fi

for tool_name in "${tools_to_show_versions[@]}"; do
  echo "$tool_name version:"
  ( set -x; "$tool_name" --version )
  echo
done

if cmake --version | grep -E "^cmake version 3.19.1$"; then
  log "CMake 3.19.1 is not supported"
  log "See https://gitlab.kitware.com/cmake/cmake/-/issues/21529 for more details."
  exit 1
fi

# -------------------------------------------------------------------------------------------------
# Check for errors in Python code of this repository
# -------------------------------------------------------------------------------------------------

( set -x; "$YB_THIRDPARTY_DIR/check_python_code.sh" )

# -------------------------------------------------------------------------------------------------

if [[ -n ${CIRCLE_PULL_REQUEST:-} ]]; then
  echo "CIRCLE_PULL_REQUEST is set: $CIRCLE_PULL_REQUEST. Will not upload artifacts."
  unset GITHUB_TOKEN
elif [[ -z ${GITHUB_TOKEN:-} || $GITHUB_TOKEN == *githubToken* ]]; then
  echo "This must be a pull request build. Will not upload artifacts."
  GITHUB_TOKEN=""
else
  echo "This is an official branch build. Will upload artifacts."
fi

# -------------------------------------------------------------------------------------------------

original_repo_dir=$PWD
git_sha1=$( git rev-parse HEAD )
tag=v$( date +%Y%m%d%H%M%S )-${git_sha1:0:10}

archive_dir_name=yugabyte-db-thirdparty-$tag
if [[ -n $YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX ]]; then
  effective_suffix="-$YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX"
else
  effective_suffix="-$os_name"
fi
archive_dir_name+=$effective_suffix
tag+=$effective_suffix

build_dir_parent=/opt/yb-build/thirdparty
repo_dir=$build_dir_parent/$archive_dir_name

( set -x; git remote -v )

origin_url=$( git config --get remote.origin.url )
if [[ -z $origin_url ]]; then
  fatal "Could not get URL of the 'origin' remote in $PWD"
fi

(
  set -x
  mkdir -p "$build_dir_parent"
  git clone "$original_repo_dir" "$repo_dir"
  ( cd "$original_repo_dir" && git diff ) | ( cd "$repo_dir" && patch -p1 )
  cd "$repo_dir"
  git remote set-url origin "$origin_url"
)

echo "Building YugabyteDB third-party code in $repo_dir"

echo "Current directory"
pwd
echo

echo "Free disk space in current directory:"
df -H .
echo

echo "Free disk space on all volumes:"
df -H
echo

cd "$repo_dir"

# We intentionally don't escape variables here so they get split into multiple arguments.
build_thirdparty_cmd_str=./build_thirdparty.sh
if [[ -n ${YB_BUILD_THIRDPARTY_ARGS:-} ]]; then
  build_thirdparty_cmd_str+=" $YB_BUILD_THIRDPARTY_ARGS"
fi

if [[ -n ${YB_BUILD_THIRDPARTY_EXTRA_ARGS:-} ]]; then
  build_thirdparty_cmd_str+=" $YB_BUILD_THIRDPARTY_EXTRA_ARGS"
fi

(
  if [[ -n ${YB_LINUXBREW_DIR:-} ]]; then
    export PATH=$YB_LINUXBREW_DIR/bin:$PATH
  fi
  set -x
  time $build_thirdparty_cmd_str
)

log "Build finished. See timing information above."

# -------------------------------------------------------------------------------------------------
# Cleanup
# -------------------------------------------------------------------------------------------------

( set -x; find . -name "*.pyc" -exec rm -f {} \; )

# -------------------------------------------------------------------------------------------------
# Archive creation and upload
# -------------------------------------------------------------------------------------------------

cd "$build_dir_parent"

archive_tarball_name=$archive_dir_name.tar.gz
archive_tarball_path=$PWD/$archive_tarball_name

log "Creating archive: $archive_tarball_name"
(
  set -x
  time tar \
    --exclude "$archive_dir_name/.git" \
    --exclude "$archive_dir_name/src" \
    --exclude "$archive_dir_name/build" \
    --exclude "$archive_dir_name/venv" \
    --exclude "$archive_dir_name/download" \
    -czf \
    "$archive_tarball_name" \
    "$archive_dir_name"
)
log "Finished creating archive: $archive_tarball_name. See timing information above."

compute_sha256sum "$archive_tarball_path"
log "Computed SHA256 sum of the archive: $sha256_sum"
echo -n "$sha256_sum" >"$archive_tarball_path.sha256"

if [[ -n ${GITHUB_TOKEN:-} ]]; then
  cd "$repo_dir"
  (
    set -x
    hub release create "$tag" \
      -m "Release $tag" \
      -a "$archive_tarball_path" \
      -a "$archive_tarball_path.sha256" \
      -t "$git_sha1"
  )
else
  log "GITHUB_TOKEN is not set, skipping archive upload"
fi
