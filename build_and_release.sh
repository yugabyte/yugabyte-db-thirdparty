#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=./yb-thirdparty-common.sh
. "${BASH_SOURCE%/*}/yb-thirdparty-common.sh"

# -------------------------------------------------------------------------------------------------
# Functions
# -------------------------------------------------------------------------------------------------

install_cmake_on_macos() {
  # We need to avoid using CMake 3.19.1 and 4.x.
  local cmake_version=3.31.0
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
  expected_sha256="50d5b9f370e71c8eee87c123b7fb9272caf2bf2b372ea7c9423f10f1cd52813b"
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

echo "OSTYPE: $OSTYPE"
if [[ $OSTYPE == darwin* ]]; then
  # On macOS, add the Homebrew bin directory corresponding to the target architecture to the PATH.
  if [[ $YB_TARGET_ARCH == "x86_64" ]]; then
    homebrew_prefix=/usr/local
  elif [[ $YB_TARGET_ARCH == "arm64" ]]; then
    homebrew_prefix=/opt/homebrew
  fi
  export PATH=${homebrew_prefix}/bin:$PATH

  # Check if the Mac is using an Apple Silicon chip
  cpu_brand_string=$( /usr/sbin/sysctl -n machdep.cpu.brand_string  )
  log "CPU brand string: $cpu_brand_string"
  if [[ $cpu_brand_string == *Apple* ]]; then
    # Check if Rosetta 2 is installed
    if /usr/bin/pgrep oahd &>/dev/null; then
      log "Rosetta 2 is installed."
    else
      log "Rosetta 2 is not installed."
    fi
  else
    log "This appears to be a non-Apple Silicon Mac, not checking for Rosetta 2."
  fi

  brew_path=$homebrew_prefix/bin/brew
  if [[ -f $brew_path ]]; then
    log "Homebrew found at $brew_path"
  else
    log "Homebrew not found at $brew_path, attempting to install"

    /bin/bash -c "$(
      curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh
    )"
    if [[ ! -f $brew_path ]]; then
      fatal "Failed to install Homebrew at $brew_path"
    fi
  fi

  log "Homebrew packages explicitly installed by the user:"
  "$brew_path" leaves --installed-on-request

  homebrew_packages=(
    autoconf
    automake
    bash
    cmake
    libtool
    pkg-config
  )
  log "Installing Homebrew packages"
  time ( set -x; "$brew_path" install "${homebrew_packages[@]}" )
  log "Homebrew packages installed"

  log "New list of homebrew packages explicitly installed by the user, including newly installed:"
  ( set -x; "$brew_path" leaves --installed-on-request )

  log "Final list of all installed Homebrew packages, with versions:"
  ( set -x; "$brew_path" list --versions )
else
  log "Contents of /proc/cpuinfo:"
  cat /proc/cpuinfo
  export PATH=/usr/local/bin:$PATH
fi

# -------------------------------------------------------------------------------------------------
# Display various settings
# -------------------------------------------------------------------------------------------------

# Current user
USER=$(whoami)
log "Current user: $USER"

# PATH
log "PATH: $PATH"

YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX=${YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX:-}
log "YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX: ${YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX:-undefined}"

YB_BUILD_THIRDPARTY_ARGS=${YB_BUILD_THIRDPARTY_ARGS:-}
log "YB_BUILD_THIRDPARTY_ARGS: ${YB_BUILD_THIRDPARTY_ARGS:-undefined}"

YB_BUILD_THIRDPARTY_EXTRA_ARGS=${YB_BUILD_THIRDPARTY_EXTRA_ARGS:-}
log "YB_BUILD_THIRDPARTY_EXTRA_ARGS: ${YB_BUILD_THIRDPARTY_EXTRA_ARGS:-undefined}"

log "CPU architecture as reported by uname -m : $( uname -m )"
log "CPU architecture as reported by arch     : $( arch )"

# -------------------------------------------------------------------------------------------------
# Installed tools
# -------------------------------------------------------------------------------------------------

echo "Bash version: $BASH_VERSION"

# Not adding libtool to this list because it does not support --version.
tools_to_show_versions=(
  autoconf
  automake
  autoreconf
  cmake
  pkg-config
  "${PYTHON:-python3}"
)

if [[ $OSTYPE == darwin* ]]; then
  tools_to_show_versions+=( shasum )
elif [[ $OSTYPE == linux* && -f /etc/redhat-release ]]; then
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
# We need to avoid using CMake 3.19.1 and 4.x.
if [[ $OSTYPE == darwin* && ($cmake_version == 3.19.1 || $cmake_version == 4.*) ]]; then
  install_cmake_on_macos
  detect_cmake_version
  if [[ $cmake_version == 3.19.1 ]]; then
    fatal "CMake 3.19.1 is not supported." \
          "See https://gitlab.kitware.com/cmake/cmake/-/issues/21529 for more details."
  elif [[ $cmake_version == 4.* ]]; then
    fatal "CMake 4.x is not supported due to lack of compatibility with CMake older than 3.5."
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

branch_file_path="$YB_THIRDPARTY_DIR/branch.txt"
branch_name=""
if [[ -f ${branch_file_path} ]]; then
  branch_name=$(<"${branch_file_path}")
fi
tag=v
if [[ -n ${branch_name} ]]; then
  tag+="${branch_name}-"
fi
tag+=$( date +%Y%m%d%H%M%S )-${git_sha1:0:10}

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

GITHUB_TOKEN=${GITHUB_TOKEN:-}
if [[ -n ${GITHUB_TOKEN:-} &&
      ${GITHUB_TOKEN} =~ ^[0-9a-zA-Z_-]{40}$ ]]; then
  log "GITHUB_TOKEN is set and is exactly 40 characters long. Checking it by listing 0 issues."
  ( set -x; hub issue -L 0 )
else
  log "GITHUB_TOKEN length is ${#GITHUB_TOKEN} characters (not 40), considering it as unset."
fi

# We intentionally don't escape variables here so they get split into multiple arguments.
build_thirdparty_cmd_str="./build_thirdparty.sh --concise-output --cleanup-before-packaging"
build_thirdparty_cmd_str+=" --delete-build-dir-after"

if [[ -n ${YB_BUILD_THIRDPARTY_ARGS:-} ]]; then
  build_thirdparty_cmd_str+=" $YB_BUILD_THIRDPARTY_ARGS"
fi

if [[ -n ${YB_BUILD_THIRDPARTY_EXTRA_ARGS:-} ]]; then
  build_thirdparty_cmd_str+=" $YB_BUILD_THIRDPARTY_EXTRA_ARGS"
fi

# Intentially not quoting $build_thirdparty_cmd_str.
# shellcheck disable=SC2206
build_thirdparty_cmd_args=( $build_thirdparty_cmd_str )

if [[ -z ${YB_SKIP_UPLOAD:-} ]]; then
  build_thirdparty_cmd_args+=( --upload-as-tag "$tag" )
fi

(
  if [[ -n ${YB_LINUXBREW_DIR:-} ]]; then
    export PATH=$YB_LINUXBREW_DIR/bin:$PATH
  fi
  set -x
  "${build_thirdparty_cmd_args[@]}"
)

for file_to_copy in archive.tar.gz archive.tar.gz.sha256; do
  if [[ -f $file_to_copy ]]; then
    cp "$file_to_copy" "$original_repo_dir"
  else
    log "Warning: file $file_to_copy not found. Artifact upload may fail."
  fi
done
