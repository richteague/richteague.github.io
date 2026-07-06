#!/bin/bash
# Generates teagueCV.pdf from index.html using headless Chrome.
# The @media print rules in index.html already force a plain white,
# light-mode layout, so no HTML rewriting is needed here.
set -euo pipefail

cd "$(dirname "$0")"

HTML_FILE="index.html"
PDF_FILE="teagueCV.pdf"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --virtual-time-budget=5000 \
  --print-to-pdf="$PDF_FILE" \
  "file://$(pwd)/$HTML_FILE"

echo "Wrote $PDF_FILE"
