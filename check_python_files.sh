#!/usr/bin/env bash

set -euo pipefail
. "${BASH_SOURCE%/*}/yb-thirdparty-common.sh"

activate_virtualenv

mypy_config_path=$YB_THIRDPARTY_DIR/mypy.ini
if [[ ! -f $mypy_config_path ]]; then
  fatal "mypy configuration file not found: $mypy_config_path"
fi

cd "$YB_THIRDPARTY_DIR"

python_files=( $(
  (
    find build_definitions -name "*.py"
    find . -maxdepth 1 -name "*.py"
  ) | sort
) )

declare -i -r num_files=${#python_files[@]}

if [[ $num_files -eq 0 ]]; then
  fatal "Could not find any Python scripts to check the syntax of"
fi

log "Checking $num_files Python files"

for python_file_path in "${python_files[@]}"; do
  log "Checking if '$python_file_path' compiles"
  python3 -m py_compile "$python_file_path"
  echo >&2

  if [[ $python_file_path == build_definitions/* ]]; then
    base_name=${python_file_path##*/}
    base_name=${base_name%.py}
    log "Trying to import '$python_file_path'"
    ( set -x; python3 -c "from build_definitions import $base_name" )
    echo >&2
  fi

  log "Type-checking '$python_file_path'"
  mypy --config-file "$mypy_config_path" "$python_file_path"
  echo >&2

  log "Checking coding style in '$python_file_path'"
  pycodestyle "--config=$YB_THIRDPARTY_DIR/pycodestyle.cfg" "$python_file_path"
  echo >&2
done

log "SUCCESS checking $num_files Python source files"
