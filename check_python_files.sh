#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=./yb-thirdparty-common.sh
. "${BASH_SOURCE%/*}/yb-thirdparty-common.sh"

activate_virtualenv

export MYPYPATH=$PYTHONPATH

file_to_check_regex=${1:-}

mypy_config_path=$YB_THIRDPARTY_DIR/mypy.ini
if [[ ! -f $mypy_config_path ]]; then
  fatal "mypy configuration file not found: $mypy_config_path"
fi

cd "$YB_THIRDPARTY_DIR"

python_files=()
while IFS='' read -r line; do python_files+=( "$line" ); done < <(
  (
    find build_definitions -name "*.py"
    find python -name "*.py"
    find . -maxdepth 1 -name "*.py"
  ) | sort
)

declare -i -r num_files=${#python_files[@]}

if [[ $num_files -eq 0 ]]; then
  fatal "Could not find any Python scripts to check the syntax of"
fi

log "Checking $num_files Python files"

declare -i num_files_checked=0
for python_file_path in "${python_files[@]}"; do
  if [[ -n $file_to_check_regex &&
        ! ${python_file_path%*/} =~ $file_to_check_regex ]]; then
    log "Skipping file $python_file_path: does not match regex $file_to_check_regex"
    continue
  fi
  log "Checking if '$python_file_path' compiles"
  python3 -m py_compile "$python_file_path"
  echo >&2

  if [[ $python_file_path == build_definitions/* ]]; then
    base_name=${python_file_path##*/}
    base_name=${base_name%.py}
    log "Trying to import '$python_file_path' from build_definitions"
    ( set -x; python3 -c "from build_definitions import $base_name" )
    echo >&2
  fi

  if [[ $python_file_path == python/yugabyte_db_thirdparty/* ]]; then
    base_name=${python_file_path##*/}
    base_name=${base_name%.py}
    log "Trying to import '$python_file_path' from yugabyte_db_thirdparty"
    ( set -x; python3 -c "from yugabyte_db_thirdparty import $base_name" )
    echo >&2
  fi

  log "Type-checking '$python_file_path'"
  mypy --config-file "$mypy_config_path" "$python_file_path"
  echo >&2

  log "Checking coding style in '$python_file_path'"
  pycodestyle "--config=$YB_THIRDPARTY_DIR/pycodestyle.cfg" "$python_file_path"
  echo >&2

  (( num_files_checked+=1 ))
done

log "SUCCESS checking $num_files_checked files out of total $num_files Python source files"
