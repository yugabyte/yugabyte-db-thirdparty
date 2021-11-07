#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=./yb-thirdparty-common.sh
. "${BASH_SOURCE%/*}/yb-thirdparty-common.sh"

# -------------------------------------------------------------------------------------------------
# Functions
# -------------------------------------------------------------------------------------------------

install_cmake_on_macos() {
  # We need to avoid using CMake 3.19.1.
  #
  local cmake_version=3.19.3
  local cmake_dir_name=cmake-${cmake_version}-macos-universal
  local cmake_tarball_name=${cmake_dir_name}.tar.gz
  local cmake_download_base_url=https://github.com/Kitware/CMake/releases/download
  local cmake_url=${cmake_download_base_url}/v${cmake_version}/${cmake_tarball_name}
  local top_dir=/opt/yb-build/cmake
  sudo mkdir -p "$top_dir"
  sudo chown "$USER" "$top_dir"
  sudo chmod 0755 "$top_dir"
  local old_dir=$PWD
  cd "$top_dir"

  log "Downloading '$cmake_url' to '$PWD/$cmake_tarball_name'"
  curl -LO "$cmake_url"
  local actual_sha256
  actual_sha256=$( shasum -a 256 "$cmake_tarball_name" | awk '{print $1}' )
  log "Actual checksum of '$cmake_tarball_name': $actual_sha256"
  expected_sha256="a6b79ad05f89241a05797510e650354d74ff72cc988981cdd1eb2b3b2bda66ac"
  if [[ $actual_sha256 != "$expected_sha256" ]]; then
    fatal "Wrong SHA256 for CMake: $actual_sha256, expected: $expected_sha256"
  fi
  tar xzf "$cmake_tarball_name"
  local cmake_bin_path=$PWD/$cmake_dir_name/CMake.app/Contents/bin
  if [[ ! -d $cmake_bin_path ]]; then
    fatal "Directory does not exist: $cmake_bin_path"
  fi
  export PATH=$cmake_bin_path:$PATH
  rm -f "$cmake_tarball_name"
  log "Installed CMake at $cmake_bin_path"
  cd "$old_dir"
}

detect_cmake_version() {
  cmake_version=$( cmake --version | grep '^cmake version ' | awk '{print $NF}' )
  if [[ -z $cmake_version ]]; then
    fatal "Failed to determine CMake version."
  fi
}

# This may re-execute the current script using the "arch" command based on YB_TARGET_ARCH.
ensure_correct_mac_architecture "$@"

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
  python3
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

detect_cmake_version
unsupported_cmake_version=3.19.1
if [[ $is_mac == "true" && $cmake_version == "$unsupported_cmake_version" ]]; then
  install_cmake_on_macos
  detect_cmake_version
  if [[ $cmake_version == "$unsupported_cmake_version" ]]; then
    fatal "CMake 3.19.1 is not supported." \
          "See https://gitlab.kitware.com/cmake/cmake/-/issues/21529 for more details."
  fi

  log "Newly installed CMake version:"
  ( set -x; cmake --version )
fi

# -------------------------------------------------------------------------------------------------
# Check for errors in Python code of this repository
# -------------------------------------------------------------------------------------------------

( set -x; "$YB_THIRDPARTY_DIR/check_code.sh" )

# -------------------------------------------------------------------------------------------------

if [[ -z ${GITHUB_TOKEN:-} || $GITHUB_TOKEN == *githubToken* ]]; then
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
if [[ -z ${YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX:-} ]]; then
  fatal "YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX is not specified."
fi
to_append="-$YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX"
archive_dir_name+=$to_append
tag+=$to_append

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

if [[ -n ${GITHUB_TOKEN:-} ]]; then
  log "GITHUB_TOKEN is set. Checking it by listing 0 issues."
  ( set -x; hub issue -L 0 )
else
  log "GITHUB_TOKEN is not set, not checking it."
fi

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
  time $build_thirdparty_cmd_str --upload-as-tag "$tag"
)

for file_to_copy in archive.tar.gz archive.tar.gz.sha256; do
  if [[ -f $file_to_copy ]]; then
    cp "$file_to_copy" "$original_repo_dir"
  else
    log "Warning: file $file_to_copy not found. Artifact upload may fail."
  fi
done