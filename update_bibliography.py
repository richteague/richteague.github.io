#!/usr/bin/env python3
"""
Regenerate the "Refereed Publications" section of teagueCV.html from a
NASA/ADS public library.

Requires:
    pip install requests
    export ADS_API_TOKEN=...   (get one at https://ui.adsabs.harvard.edu/user/settings/token)

Usage:
    python3 update_bibliography.py
    python3 update_bibliography.py --library uxd2UZZ5QSGSqcI7i3llMQ
    python3 update_bibliography.py --dry-run     # print the new section, don't touch the file

Notes / known limitations (check the diff before committing):
  - Author lists are abbreviated to "Last, F. M." (first author) / "F. M. Last"
    (later authors), truncated to "A, B, C, et al." beyond 3 authors. This is a
    best-effort reproduction of the CV's existing house style, not a byte-exact
    match for unusual cases (hyphenated names, suffixes, etc).
  - "R. Teague" (any case/position) is bolded via <strong>, matching the
    existing convention of highlighting your own name in co-author lists.
  - Venue formatting assumes "<Journal>, <volume>, <page>" for refereed work
    and "arXiv e-prints, arXiv:XXXXX.XXXXX" for preprints. Book chapters /
    conference proceedings with unusual ADS metadata may need a manual tweak.
  - Ordering: newest first by ADS pubdate, grouped by year, numbered from the
    total count down to 1 (matching the existing numbering scheme).
"""
import argparse
import os
import re
import sys
from collections import defaultdict

try:
    import requests
except ImportError:
    sys.exit("This script needs the 'requests' package: pip install requests")

ADS_API = "https://api.adsabs.harvard.edu/v1"
DEFAULT_LIBRARY_ID = "uxd2UZZ5QSGSqcI7i3llMQ"  # https://ui.adsabs.harvard.edu/public-libraries/uxd2UZZ5QSGSqcI7i3llMQ
SELF_SURNAME = "teague"
FIELDS = "bibcode,title,author,year,pub,volume,page,identifier,pubdate,doctype"
CHUNK_SIZE = 50

HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "teagueCV.html")


def die(msg):
    sys.exit(f"error: {msg}")


def get_token():
    token = os.environ.get("ADS_API_TOKEN")
    if not token:
        die(
            "ADS_API_TOKEN is not set.\n"
            "  1. Get a token at https://ui.adsabs.harvard.edu/user/settings/token\n"
            "  2. export ADS_API_TOKEN=your_token_here"
        )
    return token


def fetch_library_bibcodes(session, library_id):
    bibcodes = []
    start = 0
    rows = 100
    while True:
        resp = session.get(
            f"{ADS_API}/biblib/libraries/{library_id}",
            params={"start": start, "rows": rows},
        )
        if resp.status_code != 200:
            die(f"failed to fetch library {library_id}: {resp.status_code} {resp.text}")
        data = resp.json()
        docs = data.get("documents", [])
        bibcodes.extend(docs)
        num_documents = data.get("metadata", {}).get("num_documents", len(bibcodes))
        start += len(docs)
        if not docs or start >= num_documents:
            break
    return bibcodes


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def fetch_metadata(session, bibcodes):
    records = []
    for chunk in chunked(bibcodes, CHUNK_SIZE):
        query = " OR ".join(f'bibcode:"{b}"' for b in chunk)
        resp = session.get(
            f"{ADS_API}/search/query",
            params={"q": query, "fl": FIELDS, "rows": len(chunk)},
        )
        if resp.status_code != 200:
            die(f"search query failed: {resp.status_code} {resp.text}")
        records.extend(resp.json()["response"]["docs"])
    return records


def html_escape_bare_amp(text):
    return re.sub(r"&(?!amp;|ndash;|mdash;|middot;|rsquo;|ldquo;|rdquo;|#\d+;|[a-zA-Z]+;)", "&amp;", text)


def normalize_title(title):
    if not title:
        return ""
    t = title[0] if isinstance(title, list) else title
    t = re.sub(r"<SUP>", "<sup>", t, flags=re.I)
    t = re.sub(r"</SUP>", "</sup>", t, flags=re.I)
    t = re.sub(r"<SUB>", "<sub>", t, flags=re.I)
    t = re.sub(r"</SUB>", "</sub>", t, flags=re.I)
    return html_escape_bare_amp(t)


def abbreviate_given_names(given):
    parts = [p for p in re.split(r"[\s.]+", given.strip()) if p]
    return " ".join(p[0].upper() + "." for p in parts)


def format_author(raw, is_first_position):
    if "," in raw:
        last, given = [p.strip() for p in raw.split(",", 1)]
    else:
        last, given = raw.strip(), ""
    initials = abbreviate_given_names(given) if given else ""
    is_self = last.lower() == SELF_SURNAME
    text = f"{last}, {initials}" if is_first_position else f"{initials} {last}".strip()
    text = html_escape_bare_amp(text)
    if is_self:
        text = f"<strong>{text}</strong>"
    return text


def format_authors(authors):
    authors = authors or []
    n = len(authors)
    shown = authors[:3] if n > 3 else authors
    formatted = [format_author(a, i == 0) for i, a in enumerate(shown)]
    if n == 0:
        return ""
    if n == 1:
        return formatted[0]
    if n == 2:
        return f"{formatted[0]} &amp; {formatted[1]}"
    if n == 3:
        return f"{formatted[0]}, {formatted[1]}, &amp; {formatted[2]}"
    return ", ".join(formatted) + ", et al."


def format_venue(rec):
    pub = rec.get("pub", "")
    if pub == "arXiv e-prints" or rec.get("doctype") == "eprint":
        arxiv_id = next(
            (i.split(":", 1)[1] for i in rec.get("identifier", []) if i.startswith("arXiv:")),
            None,
        )
        if arxiv_id:
            return f"<em>arXiv e-prints</em>, arXiv:{arxiv_id}"
        return "<em>arXiv e-prints</em>"
    volume = rec.get("volume", "")
    page = rec.get("page", [""])
    page = page[0] if isinstance(page, list) else page
    bits = [b for b in (volume, page) if b]
    tail = ", ".join(bits)
    return f"<em>{html_escape_bare_amp(pub)}</em>, {tail}" if tail else f"<em>{html_escape_bare_amp(pub)}</em>"


def sort_key(rec):
    pubdate = rec.get("pubdate", "0000-00-00")
    return (pubdate, rec.get("bibcode", ""))


def build_section_html(records):
    records = sorted(records, key=sort_key, reverse=True)
    total = len(records)
    first_author_count = sum(
        1 for r in records if (r.get("author") or [""])[0].split(",")[0].strip().lower() == SELF_SURNAME
    )

    by_year = defaultdict(list)
    for rec in records:
        year = rec.get("year", "0000")
        by_year[year].append(rec)

    lines = []
    lines.append('      <h2>Refereed Publications</h2><div class="rule"></div>')
    lines.append(
        f'      <p class="pubsummary">{total} refereed articles &middot; {first_author_count} as first author '
        "&middot; reverse chronological &middot; name in bold</p>"
    )

    num = total
    for year in sorted(by_year.keys(), reverse=True):
        year_records = by_year[year]
        lines.append('      <div class="pubgroup">')
        lines.append(
            f'        <div class="yearcol"><div class="year">{year}</div>'
            f'<div class="yearcount">{len(year_records)} paper{"s" if len(year_records) != 1 else ""}</div></div>'
        )
        lines.append('        <div class="publist">')
        for rec in year_records:
            title = normalize_title(rec.get("title"))
            authors = format_authors(rec.get("author"))
            venue = format_venue(rec)
            lines.append('        <div class="pub">')
            lines.append(f'          <div class="pubnum">{num}</div>')
            lines.append('          <div class="pubmain">')
            lines.append(f'            <div class="pubtitle">{title}</div>')
            lines.append(f'            <div class="pubauthors">{authors}</div>')
            lines.append(f'            <div class="pubvenue">{venue}</div>')
            lines.append("          </div>")
            lines.append("        </div>")
            num -= 1
        lines.append("        </div>")
        lines.append("      </div>")

    return "\n".join(lines)


def replace_section(html, new_section):
    start_marker = '<h2>Refereed Publications</h2>'
    start = html.index(start_marker)
    # walk back to the start of the line containing the <h2>
    line_start = html.rfind("\n", 0, start) + 1
    end = html.index("</section>", start)
    return html[:line_start] + new_section + "\n    " + html[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", default=DEFAULT_LIBRARY_ID, help="ADS library id")
    parser.add_argument("--dry-run", action="store_true", help="print the new section instead of writing the file")
    args = parser.parse_args()

    token = get_token()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    print(f"Fetching bibcodes from library {args.library}...", file=sys.stderr)
    bibcodes = fetch_library_bibcodes(session, args.library)
    print(f"  {len(bibcodes)} documents", file=sys.stderr)

    print("Fetching metadata...", file=sys.stderr)
    records = fetch_metadata(session, bibcodes)
    print(f"  {len(records)} records", file=sys.stderr)

    new_section = build_section_html(records)

    if args.dry_run:
        print(new_section)
        return

    with open(HTML_FILE) as f:
        html = f.read()

    backup_path = HTML_FILE + ".bak"
    with open(backup_path, "w") as f:
        f.write(html)

    updated = replace_section(html, new_section)
    with open(HTML_FILE, "w") as f:
        f.write(updated)

    print(f"Updated {HTML_FILE} ({backup_path} holds the previous version).", file=sys.stderr)
    print("Review the diff, regenerate the PDF with ./make-pdf.sh, then commit.", file=sys.stderr)


if __name__ == "__main__":
    main()
