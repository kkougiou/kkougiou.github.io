# kkougiou.github.io

Personal academic website of **Konstantinos Kougioumoutzis** — quantitative
ecologist and plant taxonomist at the Laboratory of Botany, Department of
Biology, University of Patras.

Live site: <https://kkougiou.github.io/>

## Built with

- [Hugo](https://gohugo.io/) with the [Hugo Blox](https://hugoblox.com/)
  Academic CV theme (pulled in as a Hugo Module — see `go.mod`).
- Configuration lives in `config/_default/`.
- The homepage is a single landing page defined in `content/_index.md`.

## Publications and citation metrics (auto-updated)

Publications and citation metrics are generated automatically from
[OpenAlex](https://openalex.org/) — a free, open scholarly catalogue — so the
site stays in sync without any manual editing.

- `scripts/generate_publications_openalex.py` resolves the author by ORCID
  (`0000-0002-6938-3025`), then:
  - regenerates every publication page under `content/publication/<slug>/index.md`
    with clean authors, journal, DOI, abstract, date, and type; and
  - writes `data/citations.json` (total citations, h-index, i10-index,
    publication count), which the **Research Impact** section on the homepage
    renders via `layouts/partials/blocks/citations.html`.
- The publication pages are machine-generated and carry an AUTO-GENERATED
  marker — do not edit them by hand, as they are overwritten on each run.
- `.github/workflows/update-publications.yml` runs the script every Monday
  (and on manual dispatch) and commits any changes.

### Run the update locally

```bash
pip install -r requirements.txt
python scripts/generate_publications_openalex.py
```

## Deployment

`.github/workflows/publish.yaml` builds the site with Hugo and deploys it to
GitHub Pages on every push to `main`. The publications workflow only commits
content; pushing that commit to `main` triggers this single deploy.
