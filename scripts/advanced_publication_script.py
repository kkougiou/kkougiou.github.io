#!/usr/bin/env python3
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
import time
from typing import Dict, List, Optional, Set
import yaml
import re
import requests
from PIL import Image
from io import BytesIO
from tenacity import retry, stop_after_attempt, wait_exponential
import traceback

# Constants
CACHE_DIR = Path("scripts/scholar_cache")
TRACKER_FILE = Path("scripts/publication_tracker.json")
IMAGE_SIZE = (1200, 800)  # 3:2 aspect ratio for featured images

# Get API key
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY')


def fetch_with_scraperapi(url: str) -> Optional[requests.Response]:
    """Fetch a URL using ScraperAPI."""
    if not SCRAPER_API_KEY:
        return None
    
    api_url = "https://api.scraperapi.com"
    params = {
        "api_key": SCRAPER_API_KEY,
        "url": url,
        "render": "false",
        "country_code": "us"
    }
    
    try:
        response = requests.get(api_url, params=params, timeout=60)
        return response
    except Exception as e:
        print(f"ScraperAPI request failed: {e}")
        return None


def setup_scholarly_proxy() -> bool:
    """
    Try multiple proxy strategies for scholarly.
    Returns True if successful.
    """
    from scholarly import scholarly, ProxyGenerator
    
    strategies = []
    
    # Strategy 1: ScraperAPI as proxy
    if SCRAPER_API_KEY:
        def try_scraperapi(pg):
            try:
                return pg.ScraperAPI(SCRAPER_API_KEY)
            except Exception as e:
                print(f"ScraperAPI setup error: {e}")
                return False
        strategies.append(("ScraperAPI", try_scraperapi))
    
    # Strategy 2: FreeProxies
    def try_freeproxies(pg):
        try:
            return pg.FreeProxies()
        except Exception as e:
            print(f"FreeProxies setup error: {e}")
            return False
    strategies.append(("FreeProxies", try_freeproxies))
    
    for name, setup_func in strategies:
        print(f"Trying proxy: {name}...")
        try:
            pg = ProxyGenerator()
            if setup_func(pg):
                scholarly.use_proxy(pg)
                
                # Test connection
                print(f"Testing {name}...")
                test = scholarly.search_author_id("CceadYwAAAAJ")
                if test is not None:
                    print(f"✓ {name} is working")
                    return True
                else:
                    print(f"✗ {name} returned None")
            else:
                print(f"✗ {name} setup failed")
        except Exception as e:
            print(f"✗ {name} error: {e}")
    
    return False


def parse_scholar_page(html: str) -> dict:
    """Parse Google Scholar author page HTML to extract basic info."""
    author_data = {
        'name': '',
        'publications': []
    }
    
    # Extract author name
    name_match = re.search(r'<div id="gsc_prf_in"[^>]*>([^<]+)</div>', html)
    if name_match:
        author_data['name'] = name_match.group(1).strip()
    
    # Extract publications
    pub_pattern = r'<tr class="gsc_a_tr"[^>]*>.*?<a[^>]*href="(/citations\?[^"]*)"[^>]*>([^<]+)</a>.*?<div class="gs_gray">([^<]*)</div>.*?<div class="gs_gray">([^<]*)</div>.*?<span class="gsc_a_h gsc_a_hc gs_ibl">(\d*)</span>.*?<span[^>]*>(\d*)</span>'
    
    for match in re.finditer(pub_pattern, html, re.DOTALL):
        pub = {
            'url_path': match.group(1),
            'title': match.group(2).strip(),
            'authors': match.group(3).strip(),
            'venue': match.group(4).strip(),
            'citations': match.group(5).strip() or '0',
            'year': match.group(6).strip() or ''
        }
        author_data['publications'].append(pub)
    
    return author_data


def parse_publication_page(html: str) -> dict:
    """Parse individual publication page HTML."""
    pub_data = {
        'bib': {}
    }
    
    # Extract title
    title_match = re.search(r'<div id="gsc_oci_title"[^>]*>.*?<a[^>]*>([^<]+)</a>', html, re.DOTALL)
    if not title_match:
        title_match = re.search(r'<div id="gsc_oci_title"[^>]*>([^<]+)</div>', html)
    if title_match:
        pub_data['bib']['title'] = title_match.group(1).strip()
    
    # Extract fields from the table
    field_pattern = r'<div class="gsc_oci_field">([^<]+)</div>\s*<div class="gsc_oci_value"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>)*[^<]*)</div>'
    
    for match in re.finditer(field_pattern, html, re.DOTALL):
        field_name = match.group(1).strip().lower()
        field_value = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        
        if 'author' in field_name:
            pub_data['bib']['author'] = field_value.replace(', ', ' and ')
        elif 'journal' in field_name:
            pub_data['bib']['journal'] = field_value
        elif 'volume' in field_name:
            pub_data['bib']['volume'] = field_value
        elif 'issue' in field_name:
            pub_data['bib']['number'] = field_value
        elif 'pages' in field_name:
            pub_data['bib']['pages'] = field_value
        elif 'publisher' in field_name:
            pub_data['bib']['publisher'] = field_value
        elif 'publication date' in field_name or 'year' in field_name:
            pub_data['bib']['pub_year'] = field_value
        elif 'description' in field_name or 'abstract' in field_name:
            pub_data['bib']['abstract'] = field_value
        elif 'book' in field_name:
            pub_data['bib']['booktitle'] = field_value
        elif 'conference' in field_name:
            pub_data['bib']['booktitle'] = field_value
    
    # Extract links
    link_pattern = r'<div class="gsc_oci_title_ggi"><a[^>]*href="([^"]+)"[^>]*>'
    link_match = re.search(link_pattern, html)
    if link_match:
        pub_data['pub_url'] = link_match.group(1)
    
    return pub_data


def get_publications_via_scraperapi(scholar_id: str) -> List[dict]:
    """Fetch publications using ScraperAPI directly."""
    print(f"Fetching publications via ScraperAPI for Scholar ID: {scholar_id}")
    
    # Fetch author page
    author_url = f"https://scholar.google.com/citations?user={scholar_id}&hl=en&cstart=0&pagesize=100"
    print(f"Fetching author page...")
    
    response = fetch_with_scraperapi(author_url)
    if not response or not response.ok:
        print(f"Failed to fetch author page: {response.status_code if response else 'No response'}")
        return []
    
    author_data = parse_scholar_page(response.text)
    print(f"Found author: {author_data.get('name', 'Unknown')}")
    print(f"Found {len(author_data['publications'])} publications")
    
    if not author_data['publications']:
        print("No publications found in HTML. Dumping sample for debugging...")
        print(response.text[:2000])
        return []
    
    # Fetch details for each publication
    publications = []
    for i, pub_basic in enumerate(author_data['publications']):
        print(f"[{i+1}/{len(author_data['publications'])}] Fetching: {pub_basic['title'][:50]}...")
        
        try:
            pub_url = f"https://scholar.google.com{pub_basic['url_path']}"
            time.sleep(2)  # Rate limiting
            
            response = fetch_with_scraperapi(pub_url)
            if response and response.ok:
                pub_data = parse_publication_page(response.text)
                
                # Merge with basic data
                if not pub_data['bib'].get('title'):
                    pub_data['bib']['title'] = pub_basic['title']
                if not pub_data['bib'].get('author'):
                    pub_data['bib']['author'] = pub_basic['authors']
                if not pub_data['bib'].get('pub_year'):
                    pub_data['bib']['pub_year'] = pub_basic['year']
                if not pub_data['bib'].get('journal'):
                    pub_data['bib']['journal'] = pub_basic['venue']
                
                publications.append(pub_data)
                print(f"  ✓ Retrieved successfully")
            else:
                # Use basic data
                pub_data = {
                    'bib': {
                        'title': pub_basic['title'],
                        'author': pub_basic['authors'],
                        'journal': pub_basic['venue'],
                        'pub_year': pub_basic['year']
                    }
                }
                publications.append(pub_data)
                print(f"  ! Using basic data only")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            # Still add with basic info
            pub_data = {
                'bib': {
                    'title': pub_basic['title'],
                    'author': pub_basic['authors'],
                    'journal': pub_basic['venue'],
                    'pub_year': pub_basic['year']
                }
            }
            publications.append(pub_data)
    
    return publications


def get_publications_via_scholarly(scholar_id: str) -> List[dict]:
    """Fetch publications using the scholarly library."""
    from scholarly import scholarly
    
    print(f"Fetching publications via scholarly for Scholar ID: {scholar_id}")
    
    try:
        print("Searching for author...")
        author = scholarly.search_author_id(scholar_id)
        
        if author is None:
            print("Author search returned None")
            return []
        
        print(f"Found author, filling profile...")
        author = scholarly.fill(author)
        
        if author is None:
            print("Author fill returned None")
            return []
        
        publications = author.get('publications', [])
        print(f"Found {len(publications)} publications")
        
        filled_publications = []
        seen_titles: Set[str] = set()
        
        for i, pub in enumerate(publications):
            try:
                print(f"[{i+1}/{len(publications)}] Filling publication details...")
                time.sleep(2)
                
                filled_pub = scholarly.fill(pub)
                if filled_pub is None:
                    continue
                
                title = filled_pub.get('bib', {}).get('title', '')
                if not title or title in seen_titles:
                    continue
                
                seen_titles.add(title)
                filled_publications.append(filled_pub)
                print(f"  ✓ {title[:50]}...")
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
        
        return filled_publications
        
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return []


def get_publications(scholar_id: str) -> List[dict]:
    """
    Try multiple methods to fetch publications.
    """
    # Method 1: Try ScraperAPI direct parsing
    if SCRAPER_API_KEY:
        print("\n=== Method 1: ScraperAPI Direct ===")
        publications = get_publications_via_scraperapi(scholar_id)
        if publications:
            return publications
        print("ScraperAPI direct method failed")
    
    # Method 2: Try scholarly with proxy
    print("\n=== Method 2: Scholarly with Proxy ===")
    if setup_scholarly_proxy():
        publications = get_publications_via_scholarly(scholar_id)
        if publications:
            return publications
        print("Scholarly with proxy failed")
    
    # Method 3: Try scholarly without proxy (last resort)
    print("\n=== Method 3: Scholarly Direct (no proxy) ===")
    publications = get_publications_via_scholarly(scholar_id)
    if publications:
        return publications
    
    print("All methods failed")
    return []


class PublicationTracker:
    def __init__(self):
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tracker_file = TRACKER_FILE
        self.processed_pubs: Dict[str, str] = self._load_tracker()

    def _load_tracker(self) -> Dict[str, str]:
        if self.tracker_file.exists():
            with open(self.tracker_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_tracker(self):
        with open(self.tracker_file, 'w', encoding='utf-8') as f:
            json.dump(self.processed_pubs, f, indent=2)

    def compute_hash(self, pub_data: dict) -> str:
        pub_str = json.dumps(pub_data, sort_keys=True)
        return hashlib.sha256(pub_str.encode()).hexdigest()

    def is_modified(self, title: str, pub_data: dict) -> bool:
        current_hash = self.compute_hash(pub_data)
        stored_hash = self.processed_pubs.get(title)
        return stored_hash != current_hash

    def update_tracker(self, title: str, pub_data: dict):
        self.processed_pubs[title] = self.compute_hash(pub_data)
        self._save_tracker()


def sanitize_filename(title: str) -> str:
    filename = re.sub(r'[^a-zA-Z0-9\s-]', '', title.lower())
    filename = re.sub(r'\s+', '-', filename.strip())
    return filename[:100]  # Limit length


def parse_year(pub_data: dict) -> str:
    current_year = datetime.now().year
    bib = pub_data.get('bib', {})
    
    # Try pub_year field
    if 'pub_year' in bib:
        year_match = re.search(r'(19|20)\d{2}', str(bib['pub_year']))
        if year_match:
            year = int(year_match.group(0))
            if 1900 <= year <= current_year:
                return str(year)
    
    # Try other fields
    for field in ['title', 'journal', 'abstract']:
        if field in bib:
            years = re.findall(r'(20\d{2}|19\d{2})', str(bib[field]))
            if years:
                for year in sorted([int(y) for y in years], reverse=True):
                    if year <= current_year:
                        return str(year)
    
    return str(current_year)


def clean_doi(url: str) -> str:
    if not url:
        return ''
    
    doi_match = re.search(r'10\.\d{4,}/[-._;()/:\w]+', url)
    if doi_match:
        return doi_match.group(0)
    
    return ''


def determine_publication_type(pub_data: dict) -> str:
    bib = pub_data.get('bib', {})
    
    if 'journal' in bib:
        return '2'  # Journal article
    elif 'booktitle' in bib:
        booktitle = bib.get('booktitle', '').lower()
        if 'conference' in booktitle or 'proceedings' in booktitle:
            return '1'  # Conference paper
        return '6'  # Book section
    elif 'arxiv' in str(bib.get('journal', '')).lower():
        return '3'  # Preprint
    else:
        return '0'  # Uncategorized


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
def fetch_publication_image(pub_data: dict) -> Optional[Image.Image]:
    try:
        pub_url = pub_data.get('pub_url', '')
        if not pub_url:
            return None
        
        response = requests.get(pub_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if response.ok:
            og_match = re.search(r'<meta property="og:image" content="([^"]+)"', response.text)
            if og_match:
                img_url = og_match.group(1)
                img_response = requests.get(img_url, timeout=10)
                if img_response.ok:
                    img = Image.open(BytesIO(img_response.content))
                    img = img.convert('RGB')
                    img.thumbnail(IMAGE_SIZE)
                    return img
    except Exception:
        pass
    return None


def create_publication_folder(pub_data: dict, base_path: str, tracker: PublicationTracker):
    try:
        bib = pub_data.get('bib', {})
        title = bib.get('title', '')
        
        if not title:
            print("  ✗ No title, skipping")
            return False
        
        if not tracker.is_modified(title, pub_data):
            print(f"  - No changes: {title[:50]}...")
            return True
        
        folder_name = sanitize_filename(title)
        if not folder_name:
            print("  ✗ Could not generate folder name")
            return False
        
        folder_path = Path(base_path) / 'content' / 'publication' / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        
        # Parse authors
        author_str = bib.get('author', '')
        authors = [a.strip() for a in author_str.split(' and ') if a.strip()] if author_str else []
        
        # Prepare front matter
        front_matter = {
            'title': title,
            'date': f"{parse_year(pub_data)}-01-01",
            'authors': authors,
            'publication_types': [determine_publication_type(pub_data)],
            'featured': False,
            'publication': bib.get('journal', '') or bib.get('booktitle', ''),
            'abstract': bib.get('abstract', ''),
            'doi': clean_doi(pub_data.get('pub_url', '')),
            'tags': [],
            'url_pdf': pub_data.get('eprint_url', ''),
            'image': {
                'caption': '',
                'focal_point': 'Smart',
                'preview_only': False
            }
        }
        
        # Try to fetch an image
        try:
            img = fetch_publication_image(pub_data)
            if img:
                img.save(folder_path / 'featured.jpg', 'JPEG', quality=85)
        except Exception:
            pass
        
        # Create index.md
        with open(folder_path / 'index.md', 'w', encoding='utf-8') as f:
            f.write('---\n')
            f.write(yaml.dump(front_matter, allow_unicode=True, default_flow_style=False))
            f.write('---\n')
        
        # Create cite.bib
        with open(folder_path / 'cite.bib', 'w', encoding='utf-8') as f:
            bib_entry = f"@article{{{folder_name},\n"
            bib_entry += f"  title = {{{title}}},\n"
            for key, value in bib.items():
                if value and key != 'title':
                    value_str = str(value).replace('{', '').replace('}', '')
                    bib_entry += f"  {key} = {{{value_str}}},\n"
            bib_entry += "}\n"
            f.write(bib_entry)
        
        tracker.update_tracker(title, pub_data)
        print(f"  ✓ Created: {title[:50]}...")
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("Google Scholar Publication Fetcher")
    print("=" * 60)
    
    SCHOLAR_ID = "CceadYwAAAAJ"
    
    print(f"Scholar ID: {SCHOLAR_ID}")
    print(f"ScraperAPI Key: {'configured' if SCRAPER_API_KEY else 'NOT FOUND'}")
    
    if not SCRAPER_API_KEY:
        print("\n⚠ WARNING: SCRAPER_API_KEY not found in environment!")
        print("Set it as a GitHub secret for best results.\n")
    
    # Initialize tracker
    tracker = PublicationTracker()
    print(f"Previously tracked: {len(tracker.processed_pubs)} publications")
    
    # Get base path
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Fetch publications
    print("\n" + "-" * 40)
    publications = get_publications(SCHOLAR_ID)
    print("-" * 40)
    
    if not publications:
        print("\n❌ ERROR: Could not fetch any publications")
        print("Check that:")
        print("  1. SCRAPER_API_KEY is set correctly in GitHub secrets")
        print("  2. Your ScraperAPI subscription is active")
        print("  3. The Scholar ID is correct")
        exit(1)
    
    # Process publications
    print(f"\nProcessing {len(publications)} publications...")
    success = 0
    failed = 0
    
    for pub in publications:
        if create_publication_folder(pub, base_path, tracker):
            success += 1
        else:
            failed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total found: {len(publications)}")
    print(f"Processed:   {success}")
    print(f"Failed:      {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
