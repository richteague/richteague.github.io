---
name: update-bibliography
description: Regenerate the Refereed Publications section of index.html from Richard Teague's NASA/ADS public library. Use when asked to update, refresh, or sync the CV's bibliography/publication list.
---

# Update Bibliography

Regenerates the "Refereed Publications" section of `index.html` from the
NASA/ADS public library, using `update_bibliography.py` in the repo root.

## Steps

1. Confirm `ADS_API_TOKEN` is set in the environment. If not, tell the user to
   get one at https://ui.adsabs.harvard.edu/user/settings/token and
   `export ADS_API_TOKEN=...` before continuing.
2. Run a dry run first so the user can sanity-check the output before it
   touches the file:
   ```
   python3 update_bibliography.py --dry-run | head -80
   ```
3. If it looks right, run it for real:
   ```
   python3 update_bibliography.py
   ```
   This writes a `index.html.bak` backup and updates `index.html` in place.
4. Diff the change (`git diff index.html`) and skim it — new papers should
   slot in at the top of their year group, numbering should still count down
   to 1, and any unusual venues (book chapters, conference proceedings) should
   be checked by eye since ADS metadata for those is inconsistent.
5. Regenerate the PDF: `./make-pdf.sh`.
6. Ask the user before committing/pushing — don't do it automatically.

## Notes

- The default library id is baked into the script
  (`uxd2UZZ5QSGSqcI7i3llMQ`, Richard's public ADS library). Override with
  `--library <id>` if it ever changes.
- Author formatting, bolding of "R. Teague", and venue formatting are
  reproduced to match the CV's existing house style — see the docstring at
  the top of `update_bibliography.py` for the exact rules and known
  limitations.
- Authors are always normalized to "Surname, A., B." even when ADS returns a
  name as "A. B. Surname" (no comma) — `format_author()` detects the
  comma-less case and reorders it.
- Each paper title links out to its ADS abstract page
  (`https://ui.adsabs.harvard.edu/abs/<bibcode>/abstract`).
