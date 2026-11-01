# kkougiou.github.io

Personal academic website of Konstantinos (Kostas) Kougioumoutzis, built with
[Hugo Blox Builder](https://hugoblox.com) (Academic CV theme) and deployed to GitHub Pages
on every push to `main`.

## Where things live

| What | File |
|---|---|
| Name, role, affiliation, social links, bio, highlights, collaborators | `content/authors/admin/_index.md` |
| Home page sections (Research cards, selected/recent publications, contact) | `content/_index.md` |
| Top menu | `config/_default/menus.yaml` |
| Site title, description shown in Google and link previews | `config/_default/hugo.yaml`, `config/_default/params.yaml` |
| CV | `static/uploads/CV.pdf` |
| Publications (one folder per paper: `index.md` + `cite.bib`) | `content/publication/` |

## Publications

Records are built from Crossref, so they carry full author lists, DOIs and working
**Cite** buttons.

**Add a paper by DOI** (needs Python and `pip install pyyaml`):

```bash
python scripts/crossref_publications.py add 10.3390/d12070270
```

**Automatic check.** Once a month the *Update Publications* GitHub Action looks on
Crossref for works by Kougioumoutzis that are not on the site and opens a pull request
with them as hidden drafts. Delete the `draft: true` line in each one you want to show,
then merge. You can also run it by hand from the *Actions* tab. GitHub pauses scheduled
Actions after 60 days without repository activity; re-enable it from the Actions tab if
that happens.

**Formatting tips**

- `title_md` holds the title with taxon names in italics (`*Stachys virgata*`); it is used
  for display, while `title` stays plain for search engines.
- `featured: true` puts a paper under *Selected publications* on the home page.
- Your name in author lists is written `K Kougioumoutzis`; it is shown in bold.
