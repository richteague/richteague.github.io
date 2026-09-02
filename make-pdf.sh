#!/bin/bash
# Generates teagueCV.pdf from index.html using headless Chrome.
# The @media print rules in index.html already force a plain white,
# light-mode layout, so no HTML rewriting is needed here.
#
#   ./make-pdf.sh                     -> teagueCV.pdf        (the public CV)
#   ./make-pdf.sh --variant promotion -> teagueCV-promotion.pdf
#   ./make-pdf.sh --funding           -> teagueCV-funding.pdf  (legacy alias)
#
# A "variant" is a local, gitignored directory of HTML fragments —
# variants/<name>/*.html — each of which declares where it belongs via a
# directive comment on its first line:
#
#   <!-- CV-OVERLAY: at-marker FUNDING_SECTION -->
#   <!-- CV-OVERLAY: replace-section "Advising &amp; Mentoring" -->
#   <!-- CV-OVERLAY: before-section "Refereed Publications" -->
#   <!-- CV-OVERLAY: after-section "Teaching" -->
#   <!-- CV-OVERLAY: replace-text "<div class="role">Some Job Title</div>" -->
#
# The four section ops splice the fragment in as a block. replace-text is
# different: it substitutes every occurrence of the target string with the
# fragment body (HTML comments stripped, remaining lines joined), for one-off
# wording changes too small to be a whole section. It errors out if the target
# isn't found, and replaces all matches -- so include enough surrounding
# markup in the target to pin down the one line you mean.
#
# Fragments are applied in filename order (hence the 10-/20-/30- prefixes)
# to a temporary build file. index.html and teagueCV.pdf are never touched,
# so the public site and its default PDF never see any of it.
#
# Section targets are matched against the literal <h2> text in index.html,
# so they must be HTML-escaped exactly as they appear there ("&amp;", not "&").
#
# A fragment containing the {{TOTAL}} placeholder gets it replaced by the sum
# of every "$N" amount on that fragment's own class="sub" lines (used by the
# Funding section's summary line).
set -euo pipefail

cd "$(dirname "$0")"

HTML_FILE="index.html"
PDF_FILE="teagueCV.pdf"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

die() { echo "error: $*" >&2; exit 1; }

FRAGMENTS=()
OPS=()
TARGETS=()

# Parse the "<!-- CV-OVERLAY: <op> <target> -->" directive out of a fragment.
parse_directive() {
  local f="$1" line op target
  line=$(awk 'match($0, /CV-OVERLAY:/) {
      s = substr($0, RSTART + RLENGTH)
      sub(/-->[[:space:]]*$/, "", s)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
      op = s; sub(/[[:space:]].*/, "", op)
      t = s; sub(/^[^[:space:]]+[[:space:]]*/, "", t)
      gsub(/^"|"$/, "", t)
      print op "\t" t
      exit
    }' "$f")
  [[ -n "$line" ]] || die "$f has no '<!-- CV-OVERLAY: ... -->' directive"
  IFS=$'\t' read -r op target <<<"$line"
  case "$op" in
    at-marker|replace-section|before-section|after-section|replace-text) ;;
    *) die "$f: unknown overlay op '$op' (expected at-marker, replace-section, before-section, after-section or replace-text)" ;;
  esac
  [[ -n "$target" ]] || die "$f: overlay op '$op' needs a target"
  FRAGMENTS+=("$f"); OPS+=("$op"); TARGETS+=("$target")
}

VARIANT=""
case "${1:-}" in
  "")
    ;;
  --funding)
    # Legacy alias, kept working: a single fragment at the FUNDING_SECTION marker.
    VARIANT="funding"
    [[ -f funding.html ]] || die "funding.html not found (it's gitignored — create it locally first)"
    FRAGMENTS=("funding.html"); OPS=("at-marker"); TARGETS=("FUNDING_SECTION")
    ;;
  --variant)
    VARIANT="${2:-}"
    [[ -n "$VARIANT" ]] || die "--variant needs a name, e.g. --variant promotion"
    dir="variants/$VARIANT"
    [[ -d "$dir" ]] || die "$dir/ not found (variants/ is gitignored — create it locally first)"
    shopt -s nullglob
    files=("$dir"/*.html)
    shopt -u nullglob
    (( ${#files[@]} )) || die "no .html fragments found in $dir/"
    for f in "${files[@]}"; do parse_directive "$f"; done
    ;;
  *)
    die "unknown option '$1' (use --variant <name>, or --funding)"
    ;;
esac

# Splices one fragment into the CV at the place its directive names.
SPLICE_AWK='
  { line[++n] = $0 }
  END {
    if (op == "replace-text") {
      # Fragment body (HTML comments and blank lines stripped) is the
      # replacement -- that drops the directive line and any explanatory
      # comment block, which may span several lines.
      while ((getline fl < frag) > 0) {
        while (1) {
          if (incomment) {
            e = index(fl, "-->")
            if (!e) { fl = ""; break }
            fl = substr(fl, e + 3); incomment = 0
          } else {
            b = index(fl, "<!--")
            if (!b) break
            e = index(substr(fl, b + 4), "-->")
            if (!e) { fl = substr(fl, 1, b - 1); incomment = 1; break }
            fl = substr(fl, 1, b - 1) substr(fl, b + 4 + e + 2)
          }
        }
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", fl)
        if (fl == "") continue
        repl = (repl == "" ? fl : repl " " fl)
      }
      if (repl == "") { print "error: " frag " has no replacement text" > "/dev/stderr"; exit 1 }
      # Built left-to-right, so a replacement containing the target is safe.
      for (i = 1; i <= n; i++) {
        out = ""; rest = line[i]
        while ((p = index(rest, target)) > 0) {
          out = out substr(rest, 1, p - 1) repl
          rest = substr(rest, p + length(target))
          hits++
        }
        line[i] = out rest
      }
      if (!hits) { print "error: text \"" target "\" not found in " FILENAME > "/dev/stderr"; exit 1 }
      for (i = 1; i <= n; i++) print line[i]
      printf "  (%d occurrence%s)\n", hits, (hits == 1 ? "" : "s") > "/dev/stderr"
      exit 0
    }
    if (op == "at-marker") {
      needle = "<!-- " target
      for (i = 1; i <= n; i++) if (index(line[i], needle)) { s = i; e = i; break }
      if (!s) { print "error: marker " target " not found in " FILENAME > "/dev/stderr"; exit 1 }
    } else {
      needle = "<h2>" target "</h2>"
      for (i = 1; i <= n; i++) if (index(line[i], needle)) { h = i; break }
      if (!h) { print "error: section " target " not found in " FILENAME > "/dev/stderr"; exit 1 }
      for (i = h; i >= 1; i--)  if (index(line[i], "<section"))   { sec = i; break }
      for (i = h; i <= n; i++)  if (index(line[i], "</section>")) { fin = i; break }
      if (!sec || !fin) { print "error: section " target " has no enclosing <section>...</section>" > "/dev/stderr"; exit 1 }
      if      (op == "replace-section") { s = sec;     e = fin }
      else if (op == "before-section")  { s = sec;     e = sec - 1 }  # empty range: insert only
      else                              { s = fin + 1; e = fin }      # after-section
    }
    for (i = 1; i <= n; i++) {
      if (i == s) while ((getline fl < frag) > 0) print fl
      if (i >= s && i <= e) continue
      print line[i]
    }
    if (s == n + 1) while ((getline fl < frag) > 0) print fl   # inserting past the last line
  }
'

if [[ -n "$VARIANT" ]]; then
  BUILD_FILE=".cv-build.html"
  FRAG_FILE=".cv-frag.html"
  trap 'rm -f "$BUILD_FILE" "$BUILD_FILE.new" "$FRAG_FILE"' EXIT

  cp "$HTML_FILE" "$BUILD_FILE"

  for i in "${!FRAGMENTS[@]}"; do
    f="${FRAGMENTS[$i]}"

    if grep -q '{{TOTAL}}' "$f"; then
      # Sum the $ amount of every entry (PI and co-I alike) in this fragment.
      TOTAL_RAW=$(grep 'class="sub"' "$f" \
        | grep -oE '\$[0-9,]+' | tr -d '$,' | awk '{s+=$1} END{print s+0}')
      TOTAL=$(awk -v n="$TOTAL_RAW" 'BEGIN{
        s = n ""; out = ""; len = length(s)
        for (i = 1; i <= len; i++) { out = out substr(s, i, 1); r = len - i; if (r > 0 && r % 3 == 0) out = out "," }
        print "$" out
      }')
      sed "s/{{TOTAL}}/$TOTAL/g" "$f" > "$FRAG_FILE"
    else
      cp "$f" "$FRAG_FILE"
    fi

    awk -v op="${OPS[$i]}" -v target="${TARGETS[$i]}" -v frag="$FRAG_FILE" \
      "$SPLICE_AWK" "$BUILD_FILE" > "$BUILD_FILE.new"
    mv "$BUILD_FILE.new" "$BUILD_FILE"
    echo "  applied ${OPS[$i]} '${TARGETS[$i]}' <- $f"
  done

  HTML_FILE="$BUILD_FILE"
  PDF_FILE="teagueCV-$VARIANT.pdf"
fi

"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --virtual-time-budget=5000 \
  --print-to-pdf="$PDF_FILE" \
  "file://$(pwd)/$HTML_FILE"

echo "Wrote $PDF_FILE"
