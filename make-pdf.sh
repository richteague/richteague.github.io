#!/bin/bash
# Generates teagueCV.pdf from index.html using headless Chrome.
# The @media print rules in index.html already force a plain white,
# light-mode layout, so no HTML rewriting is needed here.
#
# Pass --funding to splice the local, gitignored funding.html into the
# <!-- FUNDING_SECTION --> marker before rendering, producing
# teagueCV-funding.pdf instead. index.html and teagueCV.pdf are untouched
# either way, so the public site and its default PDF never see it.
set -euo pipefail

cd "$(dirname "$0")"

HTML_FILE="index.html"
PDF_FILE="teagueCV.pdf"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

if [[ "${1:-}" == "--funding" ]]; then
  FUNDING_FILE="funding.html"
  if [[ ! -f "$FUNDING_FILE" ]]; then
    echo "error: $FUNDING_FILE not found (it's gitignored — create it locally first)" >&2
    exit 1
  fi

  # Sum the $ amount of every entry (PI and co-I alike), to fill in the
  # {{TOTAL}} placeholder in funding.html's summary line.
  TOTAL_RAW=$(grep 'class="sub"' "$FUNDING_FILE" \
    | grep -oE '\$[0-9,]+' | tr -d '$,' | awk '{s+=$1} END{print s+0}')
  TOTAL=$(awk -v n="$TOTAL_RAW" 'BEGIN{
    s=n""; out=""; len=length(s)
    for(i=1;i<=len;i++){ out=out substr(s,i,1); r=len-i; if(r>0 && r%3==0) out=out"," }
    print "$" out
  }')

  BUILD_FILE=".funding-build.html"
  trap 'rm -f "$BUILD_FILE"' EXIT

  awk -v inc="$FUNDING_FILE" -v total="$TOTAL" '
    /<!-- FUNDING_SECTION/ {
      while ((getline line < inc) > 0) {
        gsub(/\{\{TOTAL\}\}/, total, line)
        print line
      }
      next
    }
    { print }
  ' "$HTML_FILE" > "$BUILD_FILE"

  HTML_FILE="$BUILD_FILE"
  PDF_FILE="teagueCV-funding.pdf"
fi

"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --virtual-time-budget=5000 \
  --print-to-pdf="$PDF_FILE" \
  "file://$(pwd)/$HTML_FILE"

echo "Wrote $PDF_FILE"
