# Public-mirror checklist

How to publish this work as a clean, standalone public repository named
`em-curve-rv`. The goal is a repo a reviewer can clone and build, with no
private artifacts and no history that references the application context.

## Exclude before publishing

- **`note/interview_prep.md`** — private interview preparation; never
  publish.
- **`PUBLIC_MIRROR.md`** — this file; it is scaffolding, not content.
- **`.env`** — real API tokens (already gitignored; confirm it is absent).
- Any working-directory or remote named after the application (the working
  copy lived under a private name). The public repo is `em-curve-rv`.

## What ships

Everything else is already public-safe: only free/public data, the
disclaimer line is present in the README and both PDFs, no employer or fund
name appears anywhere (verified: `git ls-files | xargs grep -i` for employer
and fund terms returns only the disclaimer). Committed cache CSVs make the
repo build offline.

## Publish with clean history

The development history contains milestone commits tied to this engagement.
For a public mirror, squash to a single self-contained commit on a fresh
repo rather than pushing the working branch:

```bash
# from a clean checkout of the final tree
rm -f note/interview_prep.md PUBLIC_MIRROR.md
git checkout --orphan public
git add -A
git commit -m "EM sovereign curve RV: analytics, desk note, and working paper

Nelson-Siegel-Svensson curve fitting for MX/BR/US/DE from free public
data, DV01-neutral curve-trade analytics, and two generated documents
(a desk note and an SSRN-style working paper) with no hand-typed numbers.
Views my own; all data free and public."
# create the public repo named em-curve-rv, then:
git remote add public <url-of-em-curve-rv>
git push public public:main
```

## Verify the mirror

```bash
pip install -r requirements.txt
python -m pytest                 # tests green
python scripts/build_report.py   # both PDFs rebuild from the cache
git log --oneline                # single commit, no engagement references
git ls-files | grep -i interview # empty
```
