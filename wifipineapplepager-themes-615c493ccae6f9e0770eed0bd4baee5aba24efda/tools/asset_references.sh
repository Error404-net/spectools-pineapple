#!/bin/sh

# Usage: ./asset_references.sh /path/folderA /path/folderB

A="$1"
B="$2"

if [ -z "$A" ] || [ -z "$B" ]; then
    echo "Usage: $0 /path/folderA /path/folderB"
    exit 1
fi

if [ ! -d "$A" ] || [ ! -d "$B" ]; then
    echo "Error: both arguments must be directories"
    exit 1
fi

echo "=== Cross-Reference Report ==="

# Recursively loop over all files in folder A
find "$A" -type f | while IFS= read -r FA; do
    BASENAME=$(basename "$FA")

    # Display asset path relative to A
    case "$FA" in
        "$A"/*) REL_A=${FA#"$A"/} ;;
        *)      REL_A="$FA" ;;
    esac

    echo
    echo "$REL_A:"

    # Search recursively in B for files containing the basename
    MATCHES=$(grep -R -l -F -- "$BASENAME" "$B" 2>/dev/null || true)

    if [ -z "$MATCHES" ]; then
        echo "  referenced by: NONE"
    else
        echo "  referenced by:"
        echo "$MATCHES" | while IFS= read -r FB; do
            # Show path relative to B
            case "$FB" in
                "$B"/*) REL_B=${FB#"$B"/} ;;
                *)      REL_B="$FB" ;;
            esac
            echo "    - $REL_B"
        done
    fi
done
