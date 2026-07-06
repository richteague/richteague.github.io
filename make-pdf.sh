#!/bin/bash
# Generates teagueCV.pdf from index.html using headless Chrome.
# Temporarily swaps the page background to white before printing so the
# sheet's drop shadow / margin isn't visible in the PDF, then restores it.
set -euo pipefail

cd "$(dirname "$0")"

HTML_FILE="index.html"
PDF_FILE="teagueCV.pdf"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

cp "$HTML_FILE" "$HTML_FILE.bak"
trap 'mv "$HTML_FILE.bak" "$HTML_FILE"' EXIT

sed -i '' \
  -e 's/body{background:#efece5;/body{background:#ffffff;/' \
  -e 's/background:#fdfcfa;/background:#ffffff;/' \
  "$HTML_FILE"

"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --virtual-time-budget=5000 \
  --print-to-pdf="$PDF_FILE" \
  "file://$(pwd)/$HTML_FILE"

echo "Wrote $PDF_FILE"
