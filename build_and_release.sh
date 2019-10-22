#!/usr/bin/env bash

set -euo pipefail

. "${BASH_SOURCE%/*}/yb-thirdparty-common.sh"

cat /proc/cpuinfo

# -------------------------------------------------------------------------------------------------
# OS detection
# -------------------------------------------------------------------------------------------------

os_name=""

is_ubuntu=false
is_centos=false
is_mac=false

if [[ $OSTYPE == linux* ]]; then
  if grep -q Ubuntu /etc/issue; then
    is_ubuntu=true
    os_name="ubuntu"
  fi

  if [[ -f /etc/os-release ]] && grep -q CentOS /etc/os-release; then
    is_centos=true
    os_name="centos"
  fi
elif [[ $OSTYPE == darwin* ]]; then
  is_mac=true
  os_name="macos"
fi

if [[ -z $os_name ]]; then
  echo "Failed to determine OS name. OSTYPE: $OSTYPE" >&2
  exit 1
fi

# -------------------------------------------------------------------------------------------------
# Current user
# -------------------------------------------------------------------------------------------------

USER=$(whoami)
log "Current user: $USER"

if "$is_centos"; then
  export PATH=/usr/local/bin:$PATH
fi

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
tag=v$( date +%Y%m%d%H%M%S ).${git_sha1:0:10}

archive_dir_name=yugabyte-db-thirdparty-$tag-$os_name
build_dir_parent=/opt/yb-build/thirdparty
repo_dir=$build_dir_parent/$archive_dir_name

(
  set -x
  mkdir -p "$build_dir_parent"
  git clone "$original_repo_dir" "$repo_dir"
  ( cd "$original_repo_dir" && git diff ) | ( cd "$repo_dir" && patch -p1 )
)

if ! "$is_ubuntu"; then
  # Grab a recent URL from https://github.com/YugaByte/brew-build/releases
  # TODO: handle both SSE4 vs. non-SSE4 configurations.
  linuxbrew_url=https://github.com/yugabyte/brew-build/releases/download/20191021T231003-linux/linuxbrew-20191021T231003.tar.gz
  linuxbrew_tarball_name=${linuxbrew_url##*/}
  linuxbrew_dir_name=${linuxbrew_tarball_name%.tar.gz}
  linuxbrew_parent_dir=/opt/yb-build/brew

  export YB_LINUXBREW_DIR=$linuxbrew_parent_dir/$linuxbrew_dir_name
  if [[ -d $YB_LINUXBREW_DIR ]]; then
    log "Homebrew/Linuxbrew directory already exists at $YB_LINUXBREW_DIR"
  else
    log "Downloading and installing Homebrew/Linuxbrew into a subdirectory of $linuxbrew_parent_dir"
    (
      set -x
      mkdir -p "$linuxbrew_parent_dir"
      cd "$linuxbrew_parent_dir"
      wget -q "$linuxbrew_url"
      time tar xzf "$linuxbrew_tarball_name"
    )
    log "Downloaded and installed Homebrew/Linuxbrew to $YB_LINUXBREW_DIR"

    log "Running post_install.sh"
    (
      cd "$YB_LINUXBREW_DIR"
      time ./post_install.sh
    )
  fi
fi

echo "Building YugabyteDB third-party code in $repo_dir"

cd "$repo_dir"

pip install --user virtualenv
(
  if [[ -n ${YB_LINUXBREW_DIR:-} ]]; then
    export PATH=$YB_LINUXBREW_DIR/bin:$PATH
  fi
  time ./build_thirdparty.sh
)

# -------------------------------------------------------------------------------------------------
# Cleanup
# -------------------------------------------------------------------------------------------------

find . -name "*.pyc" -exec rm -f {} \;

# -------------------------------------------------------------------------------------------------
# Archive creation and upload
# -------------------------------------------------------------------------------------------------

cd "$build_dir_parent"

archive_tarball_name=$archive_dir_name.tar.gz
archive_tarball_path=$PWD/$archive_tarball_name
tar \
  --exclude "$archive_dir_name/.git" \
  --exclude "$archive_dir_name/src" \
  --exclude "$archive_dir_name/build" \
  --exclude "$archive_dir_name/venv" \
  --exclude "$archive_dir_name/download" \
  -cvzf \
  "$archive_tarball_name" \
  "$archive_dir_name"

if [[ -n ${GITHUB_TOKEN:-} ]]; then
  cd "$repo_dir"
  ( set -x; hub release create "$tag" -m "Release $tag" -a "$archive_tarball_path" )
fi
