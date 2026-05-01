#!/usr/bin/env bash
# Usage:
#   ./palette_to_html.sh theme.json > swatches.html
# or:
#   cat theme.json | ./palette_to_html.sh > swatches.html

JSON_FILE="$1"

# If no file is given, read from stdin
if [ -z "$JSON_FILE" ]; then
    JSON_FILE="/dev/stdin"
fi

# Require jq
if ! command -v jq >/dev/null 2>&1; then
    echo "Error: jq is required but not installed." >&2
    exit 1
fi

cat <<'EOF'
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Retro Color Swatches</title>
<style>
    body {
        background: #111;
        color: #eee;
        font-family: monospace;
        padding: 20px;
    }
    .swatch-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 12px;
    }
    .swatch {
        border: 1px solid #444;
        padding: 10px;
        border-radius: 6px;
        background: #222;
    }
    .color-box {
        width: 100%;
        height: 40px;
        border-radius: 4px;
        border: 1px solid #000;
        margin-bottom: 6px;
    }
    .label {
        font-size: 13px;
        line-height: 1.3;
    }
</style>
</head>
<body>

<h1>Retro Color Swatches</h1>

<div class="swatch-grid">
EOF

# Find the first "color_palette" object anywhere in the JSON
# then emit "name|r|g|b" lines for each entry
jq -r '
  first(.. | objects | select(has("color_palette")) | .color_palette)
  | to_entries[]
  | "\(.key)|\(.value.r)|\(.value.g)|\(.value.b)"
' "$JSON_FILE" | \
while IFS='|' read -r name r g b; do
cat <<EOF
    <div class="swatch"><div class="color-box" style="background: rgb(${r},${g},${b})"></div><div class="label">${name} - rgb(${r},${g},${b})</div></div>
EOF
done

cat <<'EOF'
</div>

</body>
</html>
EOF
