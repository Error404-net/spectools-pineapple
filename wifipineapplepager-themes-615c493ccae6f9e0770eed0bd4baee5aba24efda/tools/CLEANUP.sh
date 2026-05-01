#!/bin/bash
# Cleanup script - removes all build system files, keeps only the theme
# Author: ThewitchASarz

echo "Cleaning up build system files..."
echo ""

# Remove build system scripts
rm -f BUILD_INSTRUCTIONS.md
rm -f EXECUTE_NOW.py
rm -f FIX_PNG_COLORS.md
rm -f RUN_BUILD.sh
rm -f SUMMARY.txt
rm -f THEME_BUILD_COMPLETE.md
rm -f build_neon_kawaii_theme.py
rm -f check_pillow.py
rm -f clone_theme.py
rm -f recolor_aggressive.py
rm -f recolor_pngs_fix.py
rm -f recolor_pngs_only.py
rm -f run_build_now.py

echo "✓ Build scripts removed"

# Remove extra docs from theme folder
rm -f themes/neon-kawaii/PR_SUMMARY.md
rm -f themes/neon-kawaii/THEME_COMPLETE.txt

echo "✓ Extra docs removed from theme"
echo ""
echo "Remaining files in neon-kawaii theme:"
ls -1 themes/neon-kawaii/

echo ""
echo "✓ Cleanup complete!"
echo ""
echo "Theme ready at: themes/neon-kawaii/"
echo "  • README.md"
echo "  • theme.json"
echo "  • assets/ (156 PNG files)"
echo "  • components/ (26 JSON files)"
