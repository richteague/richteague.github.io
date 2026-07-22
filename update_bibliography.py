#!/usr/bin/env python3
"""
Regenerate the "Refereed Publications" and "Most Cited Publications" sections of
index.html from a NASA/ADS public library.

Requires:
    pip install requests
    export ADS_API_TOKEN=...   (get one at https://ui.adsabs.harvard.edu/user/settings/token)

Usage:
    python3 update_bibliography.py
    python3 update_bibliography.py --library uxd2UZZ5QSGSqcI7i3llMQ
    python3 update_bibliography.py --dry-run     # print both sections, don't touch the file

Two sections are regenerated from the same ADS fetch:
  - "Refereed Publications" — the full reverse-chronological list at the bottom.
  - "Most Cited Publications" — the MOST_CITED_COUNT (default 5) papers with the
    highest ADS citation_count, shown near the top of the CV (inserted right
    after the Education section on first run, replaced in place thereafter).
    Each row shows its live citation count. Citation counts drift week to week,
    so this section will usually produce a diff on every scheduled run.

Notes / known limitations (check the diff before committing):
  - Author lists are abbreviated to "Last, F. M." (first author) / "F. M. Last"
    (later authors), truncated to "A, B, C, et al." beyond 3 authors. This is a
    best-effort reproduction of the CV's existing house style, not a byte-exact
    match for unusual cases (hyphenated names, suffixes, etc). ADS sometimes
    gives names as "F. M. Last" instead of "Last, F. M." (no comma); this is
    detected and reordered so the surname always ends up first.
  - "R. Teague" (any case/position) is bolded via <strong>, matching the
    existing convention of highlighting your own name in co-author lists.
  - Papers first-authored by a current/former Planet Formation Lab member
    (see PFL_ROSTER below) get a superscript dagger/double-dagger/section-mark
    tag prepended to the title: undergrad, graduate student (PhD or MSc), or
    postdoc respectively. Only the *first* author is checked — this marks
    papers led by a PFL mentee, not merely co-authored by one. Keep
    PFL_ROSTER in sync with the "Advising & Mentoring" section of index.html
    by hand; it is not fetched from anywhere automatically. Matching is
    surname + first-initial only
    (ADS rarely gives full given names), so a common surname (e.g. "Chen")
    can in principle collide with an unrelated author sharing that initial
    — check new tags in the diff, don't trust them blindly.
  - Venue formatting assumes "<Journal>, <volume>, <page>" for refereed work
    and "arXiv e-prints, arXiv:XXXXX.XXXXX" for preprints. Book chapters /
    conference proceedings with unusual ADS metadata may need a manual tweak.
  - Ordering: newest first by ADS pubdate, grouped by year, numbered from the
    total count down to 1 (matching the existing numbering scheme).
  - Each title links to its ADS abstract page
    (https://ui.adsabs.harvard.edu/abs/<bibcode>/abstract).
"""
import argparse
import datetime
import os
import re
import sys
import unicodedata
from collections import defaultdict

try:
    import requests
except ImportError:
    sys.exit("This script needs the 'requests' package: pip install requests")

ADS_API = "https://api.adsabs.harvard.edu/v1"
DEFAULT_LIBRARY_ID = "uxd2UZZ5QSGSqcI7i3llMQ"  # https://ui.adsabs.harvard.edu/public-libraries/uxd2UZZ5QSGSqcI7i3llMQ
SELF_SURNAME = "teague"
FIELDS = "bibcode,title,author,year,pub,volume,page,identifier,pubdate,doctype,citation_count"
CHUNK_SIZE = 50
MOST_CITED_COUNT = 5  # size of the "Most Cited Publications" section near the top of the CV

# Current/former Planet Formation Lab members whose *first-authored* papers
# get a lead-author tag. Mirrors the "Advising & Mentoring" section of
# index.html (PFL only — pre-MIT co-supervised students are excluded) plus
# EAPS-affiliated postdocs. (surname, given-name first initial, role) —
# role is one of "undergrad", "grad" (PhD or MSc), "postdoc".
PFL_ROSTER = [
    ("Albrow", "L", "grad"),
    ("Macias", "I", "grad"),
    ("Lawrence", "J", "grad"),
    ("Duraku", "M", "grad"),
    ("De'Ath", "A", "grad"),
    ("Colclasure", "A", "grad"),
    ("Im", "H", "undergrad"),
    ("Holland", "J", "undergrad"),
    ("Cusson", "E", "undergrad"),
    ("Nath", "A", "undergrad"),
    ("Chen", "C", "undergrad"),
    ("van Duzer", "A", "undergrad"),
    ("Orgel", "A", "undergrad"),
    ("Wolfer", "L", "postdoc"),  # Wölfer, matched accent-insensitively
    ("Barraza-Alfaro", "M", "postdoc"),
    ("Speedie", "J", "postdoc"),
]
PFL_SYMBOLS = {"undergrad": "†", "grad": "‡", "postdoc": "§"}  # † ‡ §
PFL_LABELS = {"undergrad": "undergraduate", "grad": "graduate student", "postdoc": "postdoc"}

HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


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
            timeout=30,
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
            timeout=30,
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


def ads_abstract_url(bibcode):
    url = f"https://ui.adsabs.harvard.edu/abs/{bibcode}/abstract"
    return url.replace("&", "%26")


def abbreviate_given_names(given):
    parts = [p for p in re.split(r"[\s.]+", given.strip()) if p]
    return " ".join(p[0].upper() + "." for p in parts)


def split_author(raw):
    raw = raw.strip()
    if "," in raw:
        last, given = [p.strip() for p in raw.split(",", 1)]
    else:
        # ADS occasionally gives "A. B. Surname" instead of "Surname, A. B."
        parts = raw.split()
        last, given = (parts[-1], " ".join(parts[:-1])) if len(parts) > 1 else (raw, "")
    return last, given


def strip_accents(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def normalize_name(s):
    return strip_accents(s).strip().lower()


def pfl_role(last, given):
    last_n = normalize_name(last)
    initial_n = normalize_name(given)[:1] if given else ""
    for surname, initial, role in PFL_ROSTER:
        surname_n = normalize_name(surname)
        candidates = {surname_n, surname_n.split()[-1]}
        if last_n in candidates and initial.lower() == initial_n:
            return role
    return None


def lead_pfl_role(authors):
    """Role of the first author, if they're a PFL mentee — used to tag the title, not the name."""
    authors = authors or []
    if not authors:
        return None
    last, given = split_author(authors[0])
    return pfl_role(last, given)


def format_author(raw, is_first_position):
    last, given = split_author(raw)
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
        1 for r in records if split_author((r.get("author") or [""])[0])[0].lower() == SELF_SURNAME
    )

    by_year = defaultdict(list)
    for rec in records:
        year = rec.get("year", "0000")
        by_year[year].append(rec)

    used_roles = set()
    body = []
    num = total
    for year in sorted(by_year.keys(), reverse=True):
        year_records = by_year[year]
        body.append('      <div class="pubgroup">')
        body.append(
            f'        <div class="yearcol"><div class="year">{year}</div>'
            f'<div class="yearcount">{len(year_records)} paper{"s" if len(year_records) != 1 else ""}</div></div>'
        )
        body.append('        <div class="publist">')
        for rec in year_records:
            title = normalize_title(rec.get("title"))
            url = ads_abstract_url(rec.get("bibcode", ""))
            authors = format_authors(rec.get("author"))
            venue = format_venue(rec)
            role = lead_pfl_role(rec.get("author"))
            title_tag = ""
            if role:
                used_roles.add(role)
                title_tag = f'<sup class="pfltag" title="Led by a PFL {PFL_LABELS[role]}">{PFL_SYMBOLS[role]}</sup>'
            body.append('        <div class="pub">')
            body.append(f'          <div class="pubnum">{num}</div>')
            body.append('          <div class="pubmain">')
            body.append(f'            <div class="pubtitle">{title_tag}<a href="{url}" target="_blank" rel="noopener">{title}</a></div>')
            body.append(f'            <div class="pubauthors">{authors}</div>')
            body.append(f'            <div class="pubvenue">{venue}</div>')
            body.append("          </div>")
            body.append("        </div>")
            num -= 1
        body.append("        </div>")
        body.append("      </div>")

    summary = (
        f"{total} refereed articles &middot; {first_author_count} as first author "
        "&middot; reverse chronological &middot; name in bold"
    )
    for role in ("undergrad", "grad", "postdoc"):
        if role in used_roles:
            summary += f" &middot; {PFL_SYMBOLS[role]} led by PFL {PFL_LABELS[role]}"

    lines = []
    lines.append('      <h2>Refereed Publications</h2><div class="rule"></div>')
    lines.append(f'      <p class="pubsummary">{summary}</p>')
    lines.extend(body)

    return "\n".join(lines)


def citation_count(rec):
    c = rec.get("citation_count", 0)
    return c if isinstance(c, int) and c > 0 else 0


def most_cited_sort_key(rec):
    # Highest citation count first; break ties by newest pubdate so the ordering
    # is deterministic (ADS returns citation_count as an int, missing for some
    # very recent papers — treated as 0 by citation_count()).
    return (citation_count(rec), rec.get("pubdate", "0000-00-00"), rec.get("bibcode", ""))


def build_most_cited_html(records, n=MOST_CITED_COUNT, as_of=None):
    """Build the 'Most Cited Publications' section: the top-n papers by ADS
    citation count, reusing the same author/venue/PFL formatting as the full
    bibliography. Rendered as <section>-less inner HTML (heading + rows), to be
    spliced into a <section> wrapper by upsert_most_cited_section()."""
    ranked = sorted(records, key=most_cited_sort_key, reverse=True)[:n]

    body = []
    for rec in ranked:
        title = normalize_title(rec.get("title"))
        url = ads_abstract_url(rec.get("bibcode", ""))
        authors = format_authors(rec.get("author"))
        venue = format_venue(rec)
        cites = citation_count(rec)
        role = lead_pfl_role(rec.get("author"))
        title_tag = ""
        if role:
            title_tag = f'<sup class="pfltag" title="Led by a PFL {PFL_LABELS[role]}">{PFL_SYMBOLS[role]}</sup>'
        label = "citation" if cites == 1 else "citations"
        body.append('      <div class="citedpub">')
        body.append(
            f'        <div class="citedcount"><div class="citednum">{cites:,}</div>'
            f'<div class="citedlabel">{label}</div></div>'
        )
        body.append('        <div class="pubmain">')
        body.append(f'          <div class="pubtitle">{title_tag}<a href="{url}" target="_blank" rel="noopener">{title}</a></div>')
        body.append(f'          <div class="pubauthors">{authors}</div>')
        body.append(f'          <div class="pubvenue">{venue}</div>')
        body.append("        </div>")
        body.append("      </div>")

    count_word = {1: "single", 2: "two", 3: "three", 4: "four", 5: "five"}.get(len(ranked), str(len(ranked)))
    summary = f"{count_word.capitalize()} most cited publications &middot; citation counts from NASA/ADS"
    if as_of:
        summary += f", updated {as_of}"

    lines = []
    lines.append('      <h2>Most Cited Publications</h2><div class="rule"></div>')
    lines.append(f'      <p class="pubsummary">{summary}</p>')
    lines.extend(body)
    return "\n".join(lines)


MOST_CITED_HEADING = "<h2>Most Cited Publications</h2>"
EDUCATION_HEADING = "<h2>Education</h2>"


def replace_most_cited_section(html, new_section):
    """Replace an existing 'Most Cited Publications' section body in place,
    preserving its surrounding <section>...</section> wrapper (mirrors
    replace_section)."""
    start = html.index(MOST_CITED_HEADING)
    line_start = html.rfind("\n", 0, start) + 1
    try:
        end = html.index("</section>", start)
    except ValueError:
        die(f"found '{MOST_CITED_HEADING}' but no closing </section> after it in {HTML_FILE}")
    return html[:line_start] + new_section + "\n    " + html[end:]


def insert_most_cited_section(html, new_section):
    """First-run bootstrap: insert a fresh 'Most Cited Publications' <section>
    immediately after the Education section, so the block lands near the top of
    the CV as intended. Subsequent runs go through replace_most_cited_section."""
    try:
        edu = html.index(EDUCATION_HEADING)
    except ValueError:
        die(
            f"could not find '{EDUCATION_HEADING}' in {HTML_FILE} — the Most Cited "
            "section is inserted right after Education; has that heading changed?"
        )
    try:
        edu_end = html.index("</section>", edu) + len("</section>")
    except ValueError:
        die(f"found '{EDUCATION_HEADING}' but no closing </section> after it in {HTML_FILE}")
    block = "\n\n    <section>\n" + new_section + "\n    </section>"
    return html[:edu_end] + block + html[edu_end:]


def upsert_most_cited_section(html, new_section):
    if MOST_CITED_HEADING in html:
        return replace_most_cited_section(html, new_section)
    return insert_most_cited_section(html, new_section)


def replace_section(html, new_section):
    start_marker = '<h2>Refereed Publications</h2>'
    try:
        start = html.index(start_marker)
    except ValueError:
        die(
            f"could not find '{start_marker}' in {HTML_FILE} — "
            "has the section heading changed?"
        )
    # walk back to the start of the line containing the <h2>
    line_start = html.rfind("\n", 0, start) + 1
    try:
        end = html.index("</section>", start)
    except ValueError:
        die(f"found '{start_marker}' but no closing </section> after it in {HTML_FILE}")
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
    as_of = datetime.date.today().strftime("%B %Y")
    most_cited_section = build_most_cited_html(records, as_of=as_of)

    if args.dry_run:
        print("<!-- ===== Most Cited Publications ===== -->")
        print(most_cited_section)
        print("\n<!-- ===== Refereed Publications ===== -->")
        print(new_section)
        return

    with open(HTML_FILE) as f:
        html = f.read()

    backup_path = HTML_FILE + ".bak"
    with open(backup_path, "w") as f:
        f.write(html)

    updated = replace_section(html, new_section)
    updated = upsert_most_cited_section(updated, most_cited_section)
    with open(HTML_FILE, "w") as f:
        f.write(updated)

    print(f"Updated {HTML_FILE} ({backup_path} holds the previous version).", file=sys.stderr)
    print("Review the diff, regenerate the PDF with ./make-pdf.sh, then commit.", file=sys.stderr)


if __name__ == "__main__":
    main()
