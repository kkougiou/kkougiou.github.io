#!/usr/bin/env python3
"""Regenerate publication pages and citation metrics from the OpenAlex API.

OpenAlex is a free, open scholarly catalogue with a stable JSON API that needs
no API key. The author is resolved by ORCID, which is the most reliable
identifier, and every publication page under ``content/publication/`` plus the
``data/citations.json`` metrics file is rebuilt from the returned records.

The publication pages are fully machine-generated: they carry an
AUTO-GENERATED marker and are overwritten on every run, so they should never be
edited by hand. Run locally with ``python scripts/generate_publications_openalex.py``
or on a schedule via ``.github/workflows/update-publications.yml``.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import requests
import yaml

# --- Configuration -----------------------------------------------------------

ORCID = "0000-0002-6938-3025"
# Contact address for the OpenAlex "polite pool" (faster, more reliable).
MAILTO = "eledil84@gmail.com"
SCHOLAR_URL = "https://scholar.google.gr/citations?user=CceadYwAAAAJ&hl=en"

# Number of most-cited works to flag as `featured: true` on the homepage.
FEATURED_COUNT = 4

API_BASE = "https://api.openalex.org"
REPO_ROOT = Path(__file__).resolve().parent.parent
PUB_DIR = REPO_ROOT / "content" / "publication"
DATA_FILE = REPO_ROOT / "data" / "citations.json"

AUTO_GENERATED_MARKER = (
    "<!-- AUTO-GENERATED from OpenAlex by scripts/generate_publications_openalex.py."
    " Manual edits will be overwritten. -->"
)

# OpenAlex work type -> Hugo Blox publication_types taxonomy id.
# (0 Uncategorized, 1 Conference paper, 2 Journal article, 3 Preprint,
#  4 Report, 5 Book, 6 Book section, 7 Thesis, 8 Patent)
PUBLICATION_TYPE_MAP = {
    "article": "2",
    "journal-article": "2",
    "review": "2",
    "book-chapter": "6",
    "book": "5",
    "monograph": "5",
    "proceedings-article": "1",
    "proceedings": "1",
    "preprint": "3",
    "posted-content": "3",
    "report": "4",
    "dissertation": "7",
    "thesis": "7",
    "peer-review": "0",
    "dataset": "0",
}


# --- HTTP helpers ------------------------------------------------------------


def _get(url: str, params: dict | None = None) -> dict:
    """GET an OpenAlex URL with the polite-pool mailto and simple retries."""
    params = dict(params or {})
    params["mailto"] = MAILTO
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:  # network / 5xx / rate limit
            last_error = error
            wait = 2 ** attempt
            print(f"  request failed ({error}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"OpenAlex request failed after retries: {url}") from last_error


# --- OpenAlex fetching -------------------------------------------------------


def fetch_author() -> dict:
    """Return the OpenAlex author record resolved by ORCID."""
    print(f"Fetching author record for ORCID {ORCID} ...")
    return _get(f"{API_BASE}/authors/orcid:{ORCID}")


def fetch_all_works(author_id: str) -> list[dict]:
    """Return every work for the author, paginating with a cursor."""
    print("Fetching works ...")
    works: list[dict] = []
    cursor = "*"
    fields = ",".join(
        [
            "id",
            "title",
            "display_name",
            "publication_year",
            "publication_date",
            "doi",
            "type",
            "primary_location",
            "authorships",
            "abstract_inverted_index",
            "cited_by_count",
            "open_access",
        ]
    )
    while cursor:
        payload = _get(
            f"{API_BASE}/works",
            {
                "filter": f"author.id:{author_id}",
                "per-page": 200,
                "cursor": cursor,
                "select": fields,
            },
        )
        works.extend(payload.get("results", []))
        cursor = payload.get("meta", {}).get("next_cursor")
    print(f"  retrieved {len(works)} works")
    return works


# --- Field extraction --------------------------------------------------------


def reconstruct_abstract(inverted_index: dict | None) -> str:
    """Rebuild plain abstract text from OpenAlex's inverted index."""
    if not inverted_index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions.append((index, word))
    positions.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positions)


def map_publication_type(openalex_type: str | None) -> str:
    return PUBLICATION_TYPE_MAP.get((openalex_type or "").lower(), "0")


def clean_doi(doi: str | None) -> str:
    """Return the bare DOI (``10.xxxx/...``) without the URL prefix."""
    if not doi:
        return ""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE)


def author_names(work: dict) -> list[str]:
    names = []
    for authorship in work.get("authorships", []):
        name = (authorship.get("author") or {}).get("display_name")
        if name:
            names.append(name)
    return names


def journal_name(work: dict) -> str:
    source = (work.get("primary_location") or {}).get("source") or {}
    return source.get("display_name") or ""


def pdf_url(work: dict) -> str:
    return (work.get("open_access") or {}).get("oa_url") or ""


def slugify(title: str) -> str:
    """Reproduce the existing folder slug convention (lowercase, hyphenated, <=100 chars)."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")[:100]
    return slug.rstrip("-")


# --- Writing -----------------------------------------------------------------


def build_front_matter(work: dict, featured: bool) -> dict:
    title = work.get("title") or work.get("display_name") or "Untitled"
    pub_date = work.get("publication_date")
    if not pub_date:
        year = work.get("publication_year")
        pub_date = f"{year}-01-01" if year else str(date.today())
    return {
        "title": title,
        "authors": author_names(work),
        "date": pub_date,
        "publication_types": [map_publication_type(work.get("type"))],
        "publication": journal_name(work),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "doi": clean_doi(work.get("doi")),
        "featured": featured,
        "tags": [],
        "url_pdf": pdf_url(work),
        "image": {"caption": "", "focal_point": "Smart", "preview_only": False},
    }


def write_publication(work: dict, featured: bool) -> str:
    title = work.get("title") or work.get("display_name") or "Untitled"
    slug = slugify(title)
    if not slug:
        return ""
    bundle = PUB_DIR / slug
    bundle.mkdir(parents=True, exist_ok=True)
    front_matter = yaml.safe_dump(
        build_front_matter(work, featured),
        sort_keys=True,
        allow_unicode=True,
        default_flow_style=False,
    )
    (bundle / "index.md").write_text(
        f"---\n{front_matter}---\n\n{AUTO_GENERATED_MARKER}\n", encoding="utf-8"
    )
    return slug


def write_citation_data(author: dict) -> None:
    stats = author.get("summary_stats") or {}
    payload = {
        "cited_by_count": author.get("cited_by_count", 0),
        "works_count": author.get("works_count", 0),
        "h_index": stats.get("h_index", 0),
        "i10_index": stats.get("i10_index", 0),
        "updated": date.today().isoformat(),
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote metrics: {payload}")


def clear_publication_bundles() -> None:
    """Remove every generated bundle, keeping the section's own _index.md."""
    if not PUB_DIR.exists():
        return
    for child in PUB_DIR.iterdir():
        if child.is_dir():
            shutil.rmtree(child)


# --- Entry point -------------------------------------------------------------


def main() -> int:
    author = fetch_author()
    author_id = author["id"].rsplit("/", 1)[-1]
    print(f"Author: {author.get('display_name')} ({author_id})")

    works = fetch_all_works(author_id)
    works_with_title = [w for w in works if (w.get("title") or w.get("display_name"))]

    featured_ids = {
        id(w)
        for w in sorted(
            works_with_title, key=lambda w: w.get("cited_by_count", 0), reverse=True
        )[:FEATURED_COUNT]
    }

    clear_publication_bundles()

    written = 0
    for work in works_with_title:
        slug = write_publication(work, featured=id(work) in featured_ids)
        if slug:
            written += 1
    print(f"Wrote {written} publication pages to {PUB_DIR}")

    write_citation_data(author)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
