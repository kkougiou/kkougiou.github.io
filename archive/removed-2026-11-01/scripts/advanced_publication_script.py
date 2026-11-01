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
from html import unescape

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


def clean_html_text(text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not text:
        return ''
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = unescape(text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_scholar_page(html: str) -> dict:
    """Parse Google Scholar author page HTML to extract basic info."""
    author_data = {
        'name': '',
        'publications': []
    }
    
    # Extract author name
    name_match = re.search(r'<div id="gsc_prf_in"[^>]*>([^<]+)</div>', html)
    if name_match:
        author_data['name'] = clean_html_text(name_match.group(1))
    
    # Find each publication row individually
    # Split by table rows first
    rows = re.findall(r'<tr class="gsc_a_tr"[^>]*>(.*?)</tr>', html, re.DOTALL)
    
    for row in rows:
        try:
            pub = {}
            
            # Extract URL and title from the link
            title_match = re.search(r'<a[^>]*href="(/citations\?[^"]*)"[^>]*class="gsc_a_at"[^>]*>([^<]+)</a>', row)
            if not title_match:
                # Try alternative pattern
                title_match = re.search(r'<a[^>]*class="gsc_a_at"[^>]*href="(/citations\?[^"]*)"[^>]*>([^<]+)</a>', row)
            if not title_match:
                # Try without class specification
                title_match = re.search(r'<a[^>]*href="(/citations\?[^"]*)"[^>]*>([^<]+)</a>', row)
            
            if not title_match:
                continue
                
            pub['url_path'] = title_match.group(1)
            pub['title'] = clean_html_text(title_match.group(2))
            
            # Extract the gray divs (authors and venue) - they appear in order
            gray_divs = re.findall(r'<div class="gs_gray">([^<]*(?:<[^>]+>[^<]*)*)</div>', row)
            
            if len(gray_divs) >= 1:
                pub['authors'] = clean_html_text(gray_divs[0])
            else:
                pub['authors'] = ''
                
            if len(gray_divs) >= 2:
                pub['venue'] = clean_html_text(gray_divs[1])
            else:
                pub['venue'] = ''
            
            # Extract citation count - look for the citation cell
            cite_match = re.search(r'<td class="gsc_a_c"[^>]*>.*?<a[^>]*>(\d+)</a>', row, re.DOTALL)
            if cite_match:
                pub['citations'] = cite_match.group(1)
            else:
                # Try span pattern
                cite_match = re.search(r'class="gsc_a_ac[^"]*"[^>]*>(\d+)<', row)
                if cite_match:
                    pub['citations'] = cite_match.group(1)
                else:
                    pub['citations'] = '0'
            
            # Extract year - look for the year cell
            year_match = re.search(r'<td class="gsc_a_y"[^>]*>.*?<span[^>]*>(\d{4})</span>', row, re.DOTALL)
            if year_match:
                pub['year'] = year_match.group(1)
            else:
                # Try alternative pattern
                year_match = re.search(r'class="gsc_a_h[^"]*"[^>]*>(\d{4})<', row)
                if year_match:
                    pub['year'] = year_match.group(1)
                else:
                    pub['year'] = ''
            
            # Only add if we have at least a title
            if pub.get('title'):
                author_data['publications'].append(pub)
                
        except Exception as e:
            print(f"  Warning: Failed to parse a publication row: {e}")
            continue
    
    return author_data


def parse_publication_page(html: str) -> dict:
    """Parse individual publication page HTML."""
    pub_data = {
        'bib': {}
    }
    
    # Extract title - try multiple patterns
    title_match = re.search(r'<div id="gsc_oci_title"[^>]*>.*?<a[^>]*>([^<]+)</a>', html, re.DOTALL)
    if not title_match:
        title_match = re.search(r'<div id="gsc_oci_title"[^>]*>\s*([^<]+?)\s*</div>', html)
    if not title_match:
        title_match = re.search(r'id="gsc_oci_title"[^>]*>([^<]+)', html)
    if title_match:
        pub_data['bib']['title'] = clean_html_text(title_match.group(1))
    
    # Extract fields from the table - look for field/value pairs
    # Pattern: field div followed by value div
    field_pattern = r'<div class="gsc_oci_field"[^>]*>([^<]+)</div>\s*<div class="gsc_oci_value"[^>]*>(.*?)</div>'
    
    for match in re.finditer(field_pattern, html, re.DOTALL):
        field_name = clean_html_text(match.group(1)).lower()
        field_value = clean_html_text(match.group(2))
        
        if not field_value:
            continue
        
        if 'author' in field_name:
            # Convert comma-separated to "and" separated for BibTeX
            pub_data['bib']['author'] = field_value.replace(', ', ' and ')
        elif field_name == 'journal':
            pub_data['bib']['journal'] = field_value
        elif field_name == 'volume':
            pub_data['bib']['volume'] = field_value
        elif field_name == 'issue':
            pub_data['bib']['number'] = field_value
        elif field_name == 'pages':
            pub_data['bib']['pages'] = field_value
        elif field_name == 'publisher':
            pub_data['bib']['publisher'] = field_value
        elif 'publication date' in field_name:
            pub_data['bib']['pub_year'] = field_value
        elif field_name == 'description':
            pub_data['bib']['abstract'] = field_value
        elif field_name == 'book':
            pub_data['bib']['booktitle'] = field_value
        elif field_name == 'conference':
            pub_data['bib']['booktitle'] = field_value
        elif 'total citations' in field_name:
            # Skip this field
            pass
    
    # Extract external link (PDF, publisher URL, etc.)
    link_pattern = r'<div class="gsc_oci_title_ggi">\s*<a[^>]*href="([^"]+)"'
    link_match = re.search(link_pattern, html)
    if link_match:
        pub_data['pub_url'] = link_match.group(1)
    
    return pub_data


def get_publications_via_scraperapi(scholar_id: str) -> List[dict]:
    """Fetch publications using ScraperAPI directly with pagination support."""
    print(f"Fetching publications via ScraperAPI for Scholar ID: {scholar_id}")
    
    all_basic_pubs = []
    author_name = ''
    cstart = 0
    page_size = 100  # Request 100, but Scholar usually returns ~20
    max_pages = 10   # Safety limit: 10 pages * ~20 pubs = ~200 max publications
    
    # Fetch all pages of publications
    for page_num in range(max_pages):
        author_url = f"https://scholar.google.com/citations?user={scholar_id}&hl=en&cstart={cstart}&pagesize={page_size}"
        print(f"Fetching page {page_num + 1} (cstart={cstart})...")
        
        response = fetch_with_scraperapi(author_url)
        if not response or not response.ok:
            print(f"Failed to fetch page {page_num + 1}: {response.status_code if response else 'No response'}")
            break
        
        author_data = parse_scholar_page(response.text)
        
        # Get author name from first page
        if page_num == 0:
            author_name = author_data.get('name', 'Unknown')
            print(f"Found author: {author_name}")
        
        page_pubs = author_data['publications']
        print(f"  Found {len(page_pubs)} publications on page {page_num + 1}")
        
        if not page_pubs:
            # No more publications
            print(f"  No more publications found. Stopping pagination.")
            break
        
        all_basic_pubs.extend(page_pubs)
        
        # Check if we got fewer than expected (last page)
        if len(page_pubs) < 20:
            print(f"  Last page reached (fewer than 20 results).")
            break
        
        # Move to next page
        cstart += len(page_pubs)
        
        # Rate limiting between pages
        time.sleep(2)
    
    print(f"\nTotal publications found across all pages: {len(all_basic_pubs)}")
    
    if not all_basic_pubs:
        print("No publications found in HTML.")
        # Save HTML for debugging
        if response:
            debug_file = CACHE_DIR / "debug_author_page.html"
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            print(f"Saved HTML to {debug_file} for debugging")
        return []
    
    # Fetch details for each publication
    publications = []
    for i, pub_basic in enumerate(all_basic_pubs):
        print(f"[{i+1}/{len(all_basic_pubs)}] Fetching: {pub_basic['title'][:50]}...")
        
        try:
            pub_url = f"https://scholar.google.com{pub_basic['url_path']}"
            time.sleep(2)  # Rate limiting
            
            response = fetch_with_scraperapi(pub_url)
            if response and response.ok:
                pub_data = parse_publication_page(response.text)
                
                # Merge with basic data (use detailed data if available, fall back to basic)
                if not pub_data['bib'].get('title'):
                    pub_data['bib']['title'] = pub_basic['title']
                if not pub_data['bib'].get('author'):
                    pub_data['bib']['author'] = pub_basic['authors'].replace(', ', ' and ')
                if not pub_data['bib'].get('pub_year') and pub_basic.get('year'):
                    pub_data['bib']['pub_year'] = pub_basic['year']
                if not pub_data['bib'].get('journal') and not pub_data['bib'].get('booktitle'):
                    pub_data['bib']['journal'] = pub_basic['venue']
                
                publications.append(pub_data)
                print(f"  ✓ Retrieved successfully")
            else:
                # Use basic data
                pub_data = {
                    'bib': {
                        'title': pub_basic['title'],
                        'author': pub_basic['authors'].replace(', ', ' and '),
                        'journal': pub_basic['venue'],
                        'pub_year': pub_basic.get('year', '')
                    }
                }
                publications.append(pub_data)
                print(f"  ! Using basic data only")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            traceback.print_exc()
            # Still add with basic info
            pub_data = {
                'bib': {
                    'title': pub_basic['title'],
                    'author': pub_basic['authors'].replace(', ', ' and '),
                    'journal': pub_basic['venue'],
                    'pub_year': pub_basic.get('year', '')
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
    
    # Try pub_year field first
    if 'pub_year' in bib:
        pub_year = str(bib['pub_year'])
        # Extract just the year (first 4 digits that look like a year)
        year_match = re.search(r'(19|20)\d{2}', pub_year)
        if year_match:
            year = int(year_match.group(0))
            if 1900 <= year <= current_year:
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
    
    journal = bib.get('journal', '').lower()
    booktitle = bib.get('booktitle', '').lower()
    
    if booktitle:
        if 'conference' in booktitle or 'proceedings' in booktitle or 'symposium' in booktitle:
            return '1'  # Conference paper
        return '6'  # Book section
    elif journal:
        if 'arxiv' in journal:
            return '3'  # Preprint
        return '2'  # Journal article
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
        
        # Parse authors - split by " and "
        author_str = bib.get('author', '')
        if author_str:
            authors = [a.strip() for a in author_str.split(' and ') if a.strip()]
        else:
            authors = []
        
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
        traceback.print_exc()
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
