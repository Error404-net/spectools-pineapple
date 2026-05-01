#!/bin/bash
DIR="${1:-.}"

find "$DIR" -type f -printf "%s %p\n" \
    | sort -n \
    | while read -r size file; do
        hsize=$(numfmt --to=iec "$size")
        printf "%10s  %s\n" "$hsize" "$file"
      done
