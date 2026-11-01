#!/usr/bin/env python3
"""
Publication helper for kkougiou.github.io, built on Crossref (free, no API key).

Replaces the old Google Scholar scraper, which produced broken records
(venue glued to the author list, duplicated years, preprint duplicates).

Usage
-----
  # Add one paper by DOI (writes content/publication/<slug>/index.md + cite.bib)
  python scripts/crossref_publications.py add 10.3390/d12070270

  # Find Crossref works by Kougioumoutzis that are not on the site yet
  # and create draft bundles for them (draft: true, so they stay hidden
  # until you review them and delete the `draft` line)
  python scripts/crossref_publications.py discover --write

  # Refresh citation counts (OpenAlex) for every paper with a DOI
  python scripts/crossref_publications.py counts

  # Fill in missing abstracts (Crossref, else OpenAlex); never overwrites yours
  python scripts/crossref_publications.py abstracts

  # Refresh profile metrics (OpenAlex, by ORCID) into data/metrics.yaml
  python scripts/crossref_publications.py metrics

  # Dump Crossref metadata for every title currently on the site (JSON)
  python scripts/crossref_publications.py enrich --out scripts/crossref_dump.json
"""
import argparse
import html
import difflib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB_DIR = ROOT / "content" / "publication"
OWN_FAMILY = "Kougioumoutzis"
UA = "kkougiou.github.io publication updater (+https://kkougiou.github.io)"
API = "https://api.crossref.org/works"
SELECT = ("DOI,title,author,container-title,short-container-title,volume,issue,"
          "page,article-number,issued,published-print,type,publisher")


# ---------------------------------------------------------------- HTTP

def http_get(url, accept="application/json", tries=4):
    import urllib.error
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1:
                raise RuntimeError(f"HTTP {e.code} for {url}: {body}") from None
            wait = 10 * (i + 1) if e.code == 429 else 3 * (i + 1)
            print(f"  HTTP {e.code}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {i + 1} after error: {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))


def crossref_query(params):
    url = API + "?" + urllib.parse.urlencode(params)
    return json.loads(http_get(url))["message"]


def crossref_work(doi):
    return json.loads(http_get(f"{API}/{urllib.parse.quote(doi)}"))["message"]


def crossref_bibtex(doi):
    try:
        return http_get(f"https://doi.org/{doi}", accept="application/x-bibtex").strip() + "\n"
    except Exception as e:  # noqa: BLE001
        print(f"  no BibTeX for {doi}: {e}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------- helpers

def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def similarity(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def slugify(title):
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s.lower())
    return re.sub(r"\s+", "-", s.strip())[:80].rstrip("-")


def year_of(work):
    """Year of the printed issue when known (what citations use), else first publication."""
    for key in ("published-print", "issued"):
        parts = (work.get(key) or {}).get("date-parts") or [[None]]
        if parts[0][0]:
            return parts[0][0]
    return None


def clean_title(t):
    t = html.unescape(re.sub(r"</?(?:scp|sub|sup|b|span)[^>]*>", "", t or ""))
    t = re.sub(r"</?i>", "*", t)  # keep italics as markdown
    return re.sub(r"\s+", " ", t).strip()


def author_names(work):
    names = []
    for a in work.get("author", []):
        given, family = a.get("given", ""), a.get("family", "")
        if family.isupper():
            family = family.title()
        initials = "".join(p[0] for p in re.split(r"[\s.\-]+", given) if p)
        names.append(f"{initials} {family}".strip() if family else a.get("name", ""))
    return names


PUB_TYPE = {  # Hugo Blox publication_types
    "journal-article": "article-journal",
    "proceedings-article": "paper-conference",
    "book-chapter": "chapter",
    "book": "book",
    "posted-content": "article",  # preprint
}


def to_front_matter(work, draft=False):
    title_md = clean_title((work.get("title") or [""])[0])
    title = title_md.replace("*", "")
    journal = html.unescape((work.get("container-title") or [""])[0])
    journal = re.split(r" - An International Journal", journal)[0]
    vol, iss = work.get("volume", ""), work.get("issue", "")
    pages = work.get("page") or work.get("article-number", "")
    venue = f"*{journal}*" if journal else ""
    if vol:
        venue += f", {vol}"
        if iss:
            venue += f"({iss})"
    if pages:
        venue += f", {pages}"
    fm = {
        "title": title,
        **({"title_md": title_md} if title_md != title else {}),
        "authors": author_names(work),
        "date": f"{year_of(work)}-01-01",
        "publication_types": [PUB_TYPE.get(work.get("type"), "article")],
        "publication": venue,
        "doi": work["DOI"].lower(),
        "featured": False,
        "abstract": "",
    }
    if draft:
        fm["draft"] = True
    return fm


def write_bundle(work, draft=False):
    import yaml  # only needed when writing
    fm = to_front_matter(work, draft)
    folder = PUB_DIR / slugify(fm["title"])
    if (folder / "index.md").exists() and not draft:
        print(f"  exists already: {folder.relative_to(ROOT)} (overwriting)")
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "index.md", "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000))
        f.write("---\n")
    bib = crossref_bibtex(fm["doi"])
    if bib:
        (folder / "cite.bib").write_text(bib, encoding="utf-8")
    print(f"  wrote {folder.relative_to(ROOT)}{' (draft)' if draft else ''}")
    return folder


def front_matter(path):
    import yaml
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---")[1]) or {}


def existing_dois():
    dois = set()
    for f in PUB_DIR.glob("*/index.md"):
        doi = str(front_matter(f).get("doi") or "").strip().lower()
        if doi:
            dois.add(doi)
    return dois


def existing_titles():
    return {f.parent.name: str(front_matter(f).get("title", ""))
            for f in PUB_DIR.glob("*/index.md")}


# ---------------------------------------------------------------- commands

def cmd_add(args):
    for doi in args.doi:
        write_bundle(crossref_work(doi), draft=args.draft)


def is_own(author):
    return (author.get("family") or "").lower() == OWN_FAMILY.lower()


def own_works():
    items, cursor = [], "*"
    while True:
        msg = crossref_query({"query.author": OWN_FAMILY, "rows": 200,
                              "select": SELECT, "cursor": cursor})
        batch = msg.get("items", [])
        items += batch
        cursor = msg.get("next-cursor")
        if not batch or not cursor or len(items) >= msg.get("total-results", 0):
            break
    return [w for w in items
            if any(is_own(a) for a in w.get("author", []))]


def cmd_discover(args):
    have_dois, have_titles = existing_dois(), list(existing_titles().values())
    new = []
    for w in own_works():
        if w["DOI"].lower() in have_dois:
            continue
        t = (w.get("title") or [""])[0]
        if any(similarity(t, h) > 0.93 for h in have_titles):
            continue
        if w.get("type") in ("peer-review", "component", "dataset"):
            continue
        new.append(w)
    for w in sorted(new, key=lambda w: year_of(w) or 0, reverse=True):
        print(f"NEW {year_of(w)} | {w['DOI']} | {(w.get('title') or [''])[0][:90]}")
        if args.write:
            write_bundle(w, draft=True)
    print(f"{len(new)} work(s) on Crossref not yet on the site.")


def cmd_enrich(args):
    out = {"matches": {}, "own_works": []}
    for folder, title in sorted(existing_titles().items()):
        try:
            msg = crossref_query({"query.bibliographic": title, "query.author": OWN_FAMILY,
                                  "rows": 5, "select": SELECT})
        except Exception as e:  # noqa: BLE001
            print(f"ERR {folder}: {e}", file=sys.stderr)
            continue
        cands = []
        for w in msg.get("items", []):
            cands.append({"score": round(similarity(title, (w.get("title") or [""])[0]), 3),
                          "work": w})
        cands.sort(key=lambda c: -c["score"])
        out["matches"][folder] = {"site_title": title, "candidates": cands[:3]}
        best = cands[0] if cands else None
        print(f"{best['score'] if best else 0:.3f} {folder[:60]}")
        time.sleep(1.2)
    out["own_works"] = own_works()
    bibs = {}
    for m in out["matches"].values():
        c = m["candidates"]
        if c and c[0]["score"] >= 0.9:
            doi = c[0]["work"]["DOI"]
            bibs[doi] = crossref_bibtex(doi)
    for w in out["own_works"]:
        if w["DOI"] not in bibs:
            bibs[w["DOI"]] = crossref_bibtex(w["DOI"])
    out["bibtex"] = bibs
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}")


def cmd_counts(args):
    """Write `citations: N` (OpenAlex cited_by_count) into each record with a DOI."""
    import datetime
    import yaml
    total, changed = 0, 0
    for f in sorted(PUB_DIR.glob("*/index.md")):
        text = f.read_text(encoding="utf-8")
        _, head, body = text.split("---", 2)
        fm = yaml.safe_load(head) or {}
        doi = str(fm.get("doi") or "").strip()
        if not doi:
            continue
        try:
            work = json.loads(http_get("https://api.openalex.org/works/doi:" + urllib.parse.quote(doi)))
        except Exception as e:  # noqa: BLE001
            print(f"  no OpenAlex record for {doi}: {e}", file=sys.stderr)
            continue
        n = int(work.get("cited_by_count") or 0)
        total += n
        if fm.get("citations") != n:
            fm["citations"] = n
            f.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000)
                         + "---" + body, encoding="utf-8")
            changed += 1
        time.sleep(0.2)
    meta = ROOT / "data" / "citations.yaml"
    meta.write_text(f"source: OpenAlex\nupdated: '{datetime.date.today().isoformat()}'\ntotal: {total}\n",
                    encoding="utf-8")
    print(f"updated {changed} record(s); {total} citations in total")


ORCID = "0000-0002-6938-3025"


def _split_fm(path):
    import yaml
    text = path.read_text(encoding="utf-8")
    _, head, body = text.split("---", 2)
    return (yaml.safe_load(head) or {}), body


def _write_fm(path, fm, body):
    import yaml
    path.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000)
                    + "---" + body, encoding="utf-8")


def jats_to_text(s):
    s = re.sub(r"<jats:title>.*?</jats:title>", "", s or "", flags=re.S)
    s = re.sub(r"</jats:p>\s*<jats:p>", "\n\n", s)
    s = re.sub(r"<jats:italic>(.*?)</jats:italic>", r"*\1*", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", s).strip()


def openalex_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for word, idx in inv.items():
        for i in idx:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos)).strip()


def cmd_abstracts(args):
    """Fill `abstract` where it is empty; text you wrote yourself is never replaced."""
    filled = 0
    for f in sorted(PUB_DIR.glob("*/index.md")):
        fm, body = _split_fm(f)
        doi = str(fm.get("doi") or "").strip()
        if not doi or str(fm.get("abstract") or "").strip():
            continue
        text = ""
        try:
            text = jats_to_text(crossref_work(doi).get("abstract", ""))
        except Exception as e:  # noqa: BLE001
            print(f"  crossref {doi}: {e}", file=sys.stderr)
        if not text:
            try:
                w = json.loads(http_get("https://api.openalex.org/works/doi:" + urllib.parse.quote(doi)))
                text = openalex_abstract(w.get("abstract_inverted_index"))
            except Exception as e:  # noqa: BLE001
                print(f"  openalex {doi}: {e}", file=sys.stderr)
        text = re.sub(r"^(Abstract|ABSTRACT)[:.]?\s*", "", text)
        if text:
            fm["abstract"] = text
            _write_fm(f, fm, body)
            filled += 1
        time.sleep(0.3)
    print(f"filled {filled} abstract(s)")


def cmd_metrics(args):
    """Write profile metrics from OpenAlex (author found by ORCID) to data/metrics.yaml."""
    import datetime
    import yaml
    a = json.loads(http_get(f"https://api.openalex.org/authors/orcid:{ORCID}"))
    stats = a.get("summary_stats") or {}
    years = sorted((c["year"], c["cited_by_count"]) for c in a.get("counts_by_year", []))
    n_pubs = sum(1 for f in PUB_DIR.glob("*/index.md") if not front_matter(f).get("draft"))
    data = {
        "source": "OpenAlex",
        "openalex_id": a.get("id", ""),
        "updated": datetime.date.today().isoformat(),
        "publications_on_site": n_pubs,
        "citations": a.get("cited_by_count", 0),
        "h_index": stats.get("h_index", 0),
        "i10_index": stats.get("i10_index", 0),
        "citations_by_year": [{"year": y, "citations": c} for y, c in years],
    }
    (ROOT / "data" / "metrics.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(yaml.safe_dump(data, sort_keys=False))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="add publication(s) by DOI")
    a.add_argument("doi", nargs="+")
    a.add_argument("--draft", action="store_true", help="mark as draft (hidden) for review")
    d = sub.add_parser("discover", help="list Crossref works not yet on the site")
    d.add_argument("--write", action="store_true", help="create draft bundles for them")
    sub.add_parser("counts", help="refresh citation counts from OpenAlex")
    sub.add_parser("abstracts", help="fill in missing abstracts")
    sub.add_parser("metrics", help="refresh profile metrics (OpenAlex)")
    e = sub.add_parser("enrich", help="dump Crossref metadata for current titles")
    e.add_argument("--out", default="scripts/crossref_dump.json")
    args = p.parse_args()
    {"add": cmd_add, "discover": cmd_discover, "enrich": cmd_enrich, "counts": cmd_counts, "abstracts": cmd_abstracts, "metrics": cmd_metrics}[args.cmd](args)


if __name__ == "__main__":
    main()
