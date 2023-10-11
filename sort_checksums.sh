#!/usr/bin/env bash

# Sort the checksums file by the file path (second column).

set -euo pipefail
checksums_file=thirdparty_src_checksums.txt
if [[ ! -f $checksums_file ]]; then
  echo >&2 "File $checksums_file not found"
  exit 1
fi
tmp_file=/tmp/$checksums_file.tmp.$RANDOM.$RANDOM.$RANDOM
LC_COLLATE=C sort -k2,2 <"$checksums_file" >"$tmp_file"
mv -f "$tmp_file" "$checksums_file"
