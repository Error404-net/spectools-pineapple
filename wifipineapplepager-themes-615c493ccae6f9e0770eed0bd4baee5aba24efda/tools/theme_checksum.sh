#!/bin/sh

# Usage:
#   ./recursive_checksums.sh <directory> <output-file>

DIR="$1"
OUTFILE="$1.list"

if [ -z "$DIR" ] || [ -z "$OUTFILE" ]; then
    echo "Usage: $0 <directory> "
    exit 1
fi

if [ ! -d "$DIR" ]; then
    echo "Error: '$DIR' is not a directory"
    exit 1
fi

TMPFILE="${OUTFILE}.tmp"

# Build checksum list
(
    cd "$DIR" || exit 1

    # List files reliably, sorted, directories excluded
    find . -type f | sort | while IFS= read -r file; do
        sha256sum "$file"
    done
) > "$TMPFILE"

mv "$TMPFILE" "$OUTFILE"

# Now checksum the checksum file itself
sha256sum "$OUTFILE" > "${OUTFILE}.sha256"

echo "Generated:"
echo "  $OUTFILE"
echo "  ${OUTFILE}.sha256"

