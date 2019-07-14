#!/usr/bin/env bash

set -euxo pipefail

cat /proc/cpuinfo
repo_dir=$PWD

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

if [[ -z ${GITHUB_TOKEN:-} || $GITHUB_TOKEN == *githubToken* ]]; then
  echo "This must be a pull request build. Will not upload artifacts."
  GITHUB_TOKEN=""
else
  echo "This is an official branch build. Will upload artifacts."
fi

if ! "$is_ubuntu"; then
  # Grab a recent URL from https://github.com/YugaByte/brew-build/releases
  linuxbrew_url=https://github.com/YugaByte/brew-build/releases/download/v0.33/linuxbrew-20190504T004257-nosse4.tar.gz
  linuxbrew_tarball_name=${linuxbrew_url##*/}
  linuxbrew_dir_name=${linuxbrew_tarball_name%.tar.gz}
  linuxbrew_parent_dir=$HOME/linuxbrew_versions
  mkdir -p "$linuxbrew_parent_dir"
  cd "$linuxbrew_parent_dir"
  wget -q "$linuxbrew_url"
  time tar xzf "$linuxbrew_tarball_name"
  export YB_LINUXBREW_DIR=$PWD/$linuxbrew_dir_name

  cd "$YB_LINUXBREW_DIR"
  time ./post_install.sh
fi

cd "$repo_dir"
pip install --user virtualenv
(
  if [[ -n ${YB_LINUXBREW_DIR:-} ]]; then
    export PATH=$YB_LINUXBREW_DIR/bin:$PATH
  fi
  # TODO: need to add --cap-add=SYS_PTRACE to Docker command line and build with ASAN/TSAN, too.
  time ./build_thirdparty.sh
)

# Cleanup
find . -name "*.pyc" -exec rm -f {} \;

git_sha1=$( git rev-parse HEAD )
tag=v$( date +%Y%m%d%H%M%S ).${git_sha1:0:10}

dir_for_archiving=$HOME/archiving_dir
mkdir -p "$dir_for_archiving"
cd "$dir_for_archiving"
archive_dir_name=yugabyte-db-thirdparty-$tag-$OSTYPE
repo_dir_when_archiving=$dir_for_archiving/$archive_dir_name
mv "$repo_dir" "$repo_dir_when_archiving"
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
mv "$repo_dir_when_archiving" "$repo_dir"

if [[ -n ${GITHUB_TOKEN:-} ]]; then
  cd "$repo_dir"
  hub release create "$tag" -m "Release $tag" -a "$archive_tarball_path"
fi
