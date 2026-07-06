# richteague.github.io

Richard Teague's CV: a single self-contained HTML file, served directly by
GitHub Pages at [richteague.github.io](https://richteague.github.io), plus a
matching PDF export and a script that syncs the publication list from ADS.

## Layout

| Path | What it is |
|---|---|
| `index.html` | The CV. All content and CSS live in this one file — edit text directly, or open it in a browser and use dev tools. |
| `teagueCV.pdf` | PDF export of `index.html`, kept in sync automatically (see CI below). |
| `fonts/` | Self-hosted Spectral + Source Serif 4 subsets (Latin only), avoiding a runtime dependency on Google Fonts. |
| `make-pdf.sh` | Regenerates `teagueCV.pdf` from `index.html` via headless Chrome. |
| `update_bibliography.py` | Regenerates the "Refereed Publications" section from a NASA/ADS public library. |
| `.github/workflows/` | CI: rebuilds the PDF on push, refreshes the bibliography weekly. |

## Editing the CV

Just edit `index.html`. The accent colour is one CSS variable (`--accent`);
dark mode is the default palette (`:root`) with light mode as an explicit
override (`:root[data-theme="light"]`) toggled by the button in the top-right
corner. Publications are plain `<div class="pub">` blocks at the bottom —
usually easier to regenerate the whole section with the bibliography script
than to hand-edit.

If you touch the print styles (`@media print`), keep them in sync with
`:root[data-theme="light"]` — both blocks are marked `PRINT-SYNC` as a
reminder.

## Regenerating the PDF

```sh
./make-pdf.sh
```

Requires Google Chrome. On a machine where it's not at the default macOS
path, point `CHROME` at the binary:

```sh
CHROME=/path/to/chrome ./make-pdf.sh
```

This normally happens automatically — see CI below.

## Refreshing the bibliography

```sh
export ADS_API_TOKEN=...   # https://ui.adsabs.harvard.edu/user/settings/token
pip install requests
python3 update_bibliography.py --dry-run   # sanity-check the output first
python3 update_bibliography.py             # writes index.html, backs up to index.html.bak
```

Check the diff — author formatting and venue parsing are best-effort (see the
script's docstring for known edge cases: hyphenated names, unusual venues,
etc). Then regenerate the PDF and commit.

This also happens automatically once a week — see CI below.

## CI

Two GitHub Actions workflows:

- **`build-pdf.yml`** — on every push to `main` that touches `index.html`,
  `fonts/`, or `make-pdf.sh`, rebuilds `teagueCV.pdf` and commits it if it
  changed. Keeps the PDF from ever drifting out of sync with the HTML.
- **`update-bibliography.yml`** — runs `update_bibliography.py` every Monday
  (or on demand via `workflow_dispatch`) and opens a PR with the result, so
  new papers land within the diff-review the script's docstring recommends
  rather than needing someone to remember to run it.

The bibliography workflow needs an `ADS_API_TOKEN` repository secret (Settings
→ Secrets and variables → Actions), and the repo needs "Allow GitHub Actions
to create and approve pull requests" enabled (Settings → Actions → General)
for it to open PRs.

## Hosting

Served by GitHub Pages from the `main` branch root — this repo must be named
exactly `richteague.github.io` for that to resolve without a `/repo-name/`
path prefix.
