#!/usr/bin/env python3
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
import time
from typing import Dict, List, Optional, Set, Tuple
import yaml
import re
from scholarly import scholarly, ProxyGenerator
import requests
from PIL import Image
from io import BytesIO
from tenacity import retry, stop_after_attempt, wait_exponential

# Constants
CACHE_DIR = Path("scripts/scholar_cache")
TRACKER_FILE = Path("scripts/publication_tracker.json")
IMAGE_SIZE = (1200, 800)  # 3:2 aspect ratio for featured images

class PublicationTracker:
    def __init__(self):
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tracker_file = TRACKER_FILE
        self.processed_pubs: Dict[str, str] = self._load_tracker()

    def _load_tracker(self) -> Dict[str, str]:
        """Load previously processed publications and their hashes."""
        if self.tracker_file.exists():
            with open(self.tracker_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_tracker(self):
        """Save processed publications tracker."""
        with open(self.tracker_file, 'w', encoding='utf-8') as f:
            json.dump(self.processed_pubs, f, indent=2)

    def compute_hash(self, pub_data: dict) -> str:
        """Compute a hash of publication data for change detection."""
        pub_str = json.dumps(pub_data, sort_keys=True)
        return hashlib.sha256(pub_str.encode()).hexdigest()

    def is_modified(self, title: str, pub_data: dict) -> bool:
        """Check if a publication has been modified since last processing."""
        current_hash = self.compute_hash(pub_data)
        stored_hash = self.processed_pubs.get(title)
        return stored_hash != current_hash

    def update_tracker(self, title: str, pub_data: dict):
        """Update tracker with latest publication hash."""
        self.processed_pubs[title] = self.compute_hash(pub_data)
        self._save_tracker()

def sanitize_filename(title: str) -> str:
    """Convert title to filename-friendly format."""
    filename = re.sub(r'[^a-zA-Z0-9\s-]', '', title.lower())
    filename = re.sub(r'\s+', '-', filename.strip())
    return filename

def extract_year_from_text(text: str) -> Optional[str]:
    """Extract year from text content."""
    if not text:
        return None
    years = re.findall(r'(20\d{2}|19\d{2})', str(text))
    if years:
        years = sorted([int(y) for y in years], reverse=True)
        current_year = datetime.now().year
        for year in years:
            if year <= current_year:
                return str(year)
    return None

def parse_year(pub_data: dict) -> str:
    """Parse year from publication data."""
    current_year = datetime.now().year
    
    # Special case handling
    title = pub_data['bib'].get('title', '').lower()
    if "taxonomic and phylogenetic plant diversity patterns of polluted metal mining sites" in title:
        return "2009"
    
    # Try to get year from pub_year field
    if 'pub_year' in pub_data['bib']:
        year_match = re.search(r'(19|20)\d{2}', str(pub_data['bib']['pub_year']))
        if year_match:
            year = int(year_match.group(0))
            if 1900 <= year <= current_year:
                return str(year)
    
    # Try various sources
    for source in ['title', 'journal', 'abstract']:
        if source in pub_data['bib']:
            year = extract_year_from_text(pub_data['bib'][source])
            if year:
                return year
    
    return str(current_year)

def clean_doi(doi: str) -> str:
    """Clean DOI by removing common prefixes and handling various URL formats."""
    if not doi:
        return ''
    
    # Special case handling
    title_lower = doi.lower()
    if "current greek protected areas fail" in title_lower:
        return "10.2139/ssrn.5014808"
    
    # Handle repository URLs
    if 'researchgate.net' in doi.lower():
        doi_match = re.search(r'10\.\d{4,}/[-._;()/:\w]+', doi)
        return doi_match.group(0) if doi_match else ''
    
    if any(domain in doi.lower() for domain in ['academia.edu', 'authorea.com']):
        return ''
    
    # Clean prefixes
    prefixes = ['https://doi.org/', 'http://doi.org/', 'doi.org/']
    for prefix in prefixes:
        while doi.startswith(prefix):
            doi = doi[len(prefix):]
    
    # Validate DOI format
    if doi.startswith(('http://', 'https://')) and not re.match(r'10\.\d{4,}/', doi):
        return ''
    
    if re.match(r'10\.\d{4,}/', doi):
        return doi
        
    return ''

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def fetch_publication_image(pub_data: dict) -> Optional[str]:
    """Attempt to fetch a relevant image for the publication."""
    try:
        # Try to get image from journal website
        if 'url' in pub_data:
            response = requests.get(pub_data['url'], timeout=10)
            if response.ok:
                # Look for Open Graph image
                og_match = re.search(r'<meta property="og:image" content="([^"]+)"', response.text)
                if og_match:
                    img_url = og_match.group(1)
                    img_response = requests.get(img_url, timeout=10)
                    if img_response.ok:
                        img = Image.open(BytesIO(img_response.content))
                        img = img.convert('RGB')
                        img.thumbnail(IMAGE_SIZE)
                        return img
    except Exception as e:
        print(f"Error fetching image: {e}")
    return None

def determine_publication_type(pub_data: dict) -> str:
    """Determine publication type according to Hugo Academic categories."""
    bib = pub_data['bib']
    
    if 'journal' in bib:
        return '2'  # Journal article
    elif 'booktitle' in bib and ('conference' in bib.get('booktitle', '').lower() or 
                                'proceedings' in bib.get('booktitle', '').lower()):
        return '1'  # Conference paper
    elif 'book' in bib.get('type', '').lower():
        return '5'  # Book
    elif 'chapter' in bib.get('type', '').lower():
        return '6'  # Book section
    elif 'thesis' in bib.get('type', '').lower():
        return '7'  # Thesis
    elif 'arxiv' in bib.get('journal', '').lower():
        return '3'  # Preprint
    else:
        return '0'  # Uncategorized

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_publications(scholar_id: str) -> List[dict]:
    """Fetch publications from Google Scholar with retry logic."""
    print(f"Fetching publications for Scholar ID: {scholar_id}")
    
    try:
        print("Searching for author...")
        author = scholarly.search_author_id(scholar_id)
        if not author:
            print(f"Error: No author found with ID: {scholar_id}")
            return []
            
        print("Found author, retrieving full profile...")
        author = scholarly.fill(author)
        print(f"Found {len(author['publications'])} publications")
        
        publications = []
        seen_titles: Set[str] = set()
        
        for pub in author['publications']:
            try:
                filled_pub = scholarly.fill(pub)
                title = filled_pub['bib']['title']
                if title in seen_titles:
                    print(f"Skipping duplicate: {title}")
                    continue
                seen_titles.add(title)
                publications.append(filled_pub)
                print(f"Retrieved: {title}")
                time.sleep(2)  # Rate limiting
            except Exception as e:
                print(f"Warning: Could not retrieve details for a publication: {e}")
        
        return publications
    except Exception as e:
        print(f"Error fetching publications: {e}")
        return []

def create_publication_folder(pub_data: dict, base_path: str, tracker: PublicationTracker):
    """Create a publication folder with index.md and cite.bib files."""
    try:
        title = pub_data['bib']['title']
        print(f"\nProcessing publication: {title}")
        
        # Check if publication needs updating
        if not tracker.is_modified(title, pub_data):
            print(f"No changes detected for: {title}")
            return
        
        folder_name = sanitize_filename(title)
        folder_path = Path(base_path) / 'content' / 'publication' / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        print(f"Created/verified folder: {folder_path}")
        
        # Prepare front matter
        print("Preparing front matter...")
        front_matter = {
            'title': title,
            'date': f"{parse_year(pub_data)}-01-01",
            'authors': [author.strip() for author in pub_data['bib'].get('author', '').split(' and ')],
            'publication_types': [determine_publication_type(pub_data)],
            'featured': False,
            'publication': pub_data['bib'].get('journal', ''),
            'abstract': pub_data.get('bib', {}).get('abstract', ''),
            'doi': clean_doi(pub_data.get('pub_url', '')),
            'tags': [],
            'url_pdf': '',
            'image': {
                'caption': '',
                'focal_point': 'Smart',
                'preview_only': False
            }
        }
        
        # Try to fetch an image
        img = fetch_publication_image(pub_data)
        if img:
            img_path = folder_path / 'featured.jpg'
            img.save(img_path, 'JPEG', quality=85)
            print(f"Saved featured image: {img_path}")
        
        # Create index.md
        with open(folder_path / 'index.md', 'w', encoding='utf-8') as f:
            f.write('---\n')
            f.write(yaml.dump(front_matter, allow_unicode=True))
            f.write('---\n')
        print(f"Created index.md")
        
        # Create cite.bib
        if 'bib' in pub_data:
            with open(folder_path / 'cite.bib', 'w', encoding='utf-8') as f:
                bib_entry = f"@article{{{folder_name},\n"
                for key, value in pub_data['bib'].items():
                    if value and key != 'title':
                        bib_entry += f"  {key} = {{{value}}},\n"
                bib_entry += "}\n"
                f.write(bib_entry)
            print(f"Created cite.bib")
        
        # Update tracker
        tracker.update_tracker(title, pub_data)
        
    except Exception as e:
        print(f"Error processing publication {pub_data['bib'].get('title', 'Unknown')}: {e}")

def main():
    # Your Google Scholar ID
    SCHOLAR_ID = "CceadYwAAAAJ"  # Konstantinos Kougioumoutzis
    
    if not SCHOLAR_ID:
        print("Please set your Google Scholar ID in the script")
        return
    
    # Initialize publication tracker
    tracker = PublicationTracker()
    
    # Get the base path
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Fetch and process publications
    publications = get_publications(SCHOLAR_ID)
    
    for pub in publications:
        create_publication_folder(pub, base_path, tracker)
        print(f"Processed: {pub['bib']['title']}")

if __name__ == "__main__":
    main()
