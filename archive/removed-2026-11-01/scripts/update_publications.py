#!/usr/bin/env python3
import os
import json
from datetime import datetime
from scholarly import scholarly, ProxyGenerator
import yaml
import re
import requests
from bs4 import BeautifulSoup
import time

def sanitize_filename(title):
    """Convert title to filename-friendly format."""
    # Remove special characters and convert to lowercase
    filename = re.sub(r'[^a-zA-Z0-9\s-]', '', title.lower())
    # Replace spaces with hyphens
    filename = re.sub(r'\s+', '-', filename.strip())
    return filename

def extract_year_from_text(text):
    """Extract year from text content."""
    # Look for years in reverse chronological order (most recent first)
    years = re.findall(r'(20\d{2}|19\d{2})', str(text))
    if years:
        # Convert to integers and sort in descending order
        years = sorted([int(y) for y in years], reverse=True)
        # Return the most recent year that's not in the future
        current_year = datetime.now().year
        for year in years:
            if year <= current_year:
                return year
    return None

def parse_year(pub_data):
    """Parse year from publication data."""
    # Handle special cases
    title = pub_data['bib'].get('title', '').lower()
    if 'taxonomic and phylogenetic plant diversity patterns of polluted metal mining sites in attika' in title:
        return 2009
    if 'current greek protected areas fail to fully capture shifting endemism hotspots' in title:
        return 2024
    
    current_year = datetime.now().year
    
    # Try to get year from pub_year field
    if 'pub_year' in pub_data['bib']:
        year_match = re.search(r'(19|20)\d{2}', str(pub_data['bib']['pub_year']))
        if year_match:
            year = int(year_match.group(0))
            if 1900 <= year <= current_year:
                return year
    
    # Try to find year in citation
    if 'citation' in pub_data['bib']:
        year = extract_year_from_text(pub_data['bib']['citation'])
        if year:
            return year
    
    # Try to find year in title
    year = extract_year_from_text(pub_data['bib']['title'])
    if year:
        return year
        
    # Try to find year in journal/venue
    if 'journal' in pub_data['bib']:
        year = extract_year_from_text(pub_data['bib']['journal'])
        if year:
            return year
            
    # Try to find year in abstract
    if 'abstract' in pub_data.get('bib', {}):
        year = extract_year_from_text(pub_data['bib']['abstract'])
        if year:
            return year
    
    # Default to current year if no valid year found
    return current_year

def clean_doi(pub_data):
    """Extract and clean DOI from publication data."""
    if not pub_data:
        return ''
        
    # Handle special cases
    title = pub_data['bib'].get('title', '').lower()
    if 'taxonomic and phylogenetic plant diversity patterns of polluted metal mining sites in attika' in title:
        return ''
    if 'current greek protected areas fail to fully capture shifting endemism hotspots' in title:
        return '10.2139/ssrn.5014808'
    
    # Try to get DOI from citation field first
    if 'citation' in pub_data.get('bib', {}):
        doi_match = re.search(r'10\.\d{4,}/[-._;()/:\w]+', pub_data['bib']['citation'])
        if doi_match:
            return doi_match.group(0)
    
    # Try to get DOI from eprint field
    if 'eprint' in pub_data.get('bib', {}):
        doi_match = re.search(r'10\.\d{4,}/[-._;()/:\w]+', pub_data['bib']['eprint'])
        if doi_match:
            return doi_match.group(0)
    
    # Try the pub_url field
    if 'pub_url' in pub_data:
        # First try to extract DOI from URL
        doi_match = re.search(r'10\.\d{4,}/[-._;()/:\w]+', pub_data['pub_url'])
        if doi_match:
            return doi_match.group(0)
            
    # Try the DOI field if it exists
    if 'doi' in pub_data.get('bib', {}):
        doi_match = re.search(r'10\.\d{4,}/[-._;()/:\w]+', pub_data['bib']['doi'])
        if doi_match:
            return doi_match.group(0)
    
    return ''

def get_publications(scholar_id):
    """Fetch publications from Google Scholar."""
    print(f"Fetching publications for Scholar ID: {scholar_id}")
    
    try:
        # Search for the author by ID
        print("Searching for author...")
        author = scholarly.search_author_id(scholar_id)
        if not author:
            print(f"Error: No author found with ID: {scholar_id}")
            return []
            
        # Fill in author details including publications
        print("Found author, retrieving full profile...")
        author = scholarly.fill(author)
        print(f"Found {len(author['publications'])} publications")
        
        # Fill details for each publication
        print("Retrieving detailed publication information...")
        publications = []
        seen_titles = set()  # Track unique titles to avoid duplicates
        
        for pub in author['publications']:
            try:
                filled_pub = scholarly.fill(pub)
                # Skip if we've already seen this title
                title = filled_pub['bib']['title']
                if title in seen_titles:
                    print(f"Skipping duplicate: {title}")
                    continue
                seen_titles.add(title)
                publications.append(filled_pub)
                print(f"Retrieved: {title}")
                # Add a small delay to avoid hitting rate limits
                time.sleep(1)
            except Exception as e:
                print(f"Warning: Could not retrieve details for a publication: {e}")
        
        print(f"Successfully retrieved {len(publications)} unique publications")
        return publications
    except Exception as e:
        print(f"Error fetching publications: {e}")
        return []

def create_publication_folder(pub_data, base_path):
    """Create a publication folder with index.md and cite.bib files."""
    try:
        # Create folder name from title
        title = pub_data['bib']['title']
        print(f"\nProcessing publication: {title}")
        folder_name = sanitize_filename(title)
        folder_path = os.path.join(base_path, 'content/publication', folder_name)
        
        # Create folder if it doesn't exist
        os.makedirs(folder_path, exist_ok=True)
        print(f"Created/verified folder: {folder_path}")
    
        # Extract year using the enhanced parse_year function
        year = parse_year(pub_data)
        date = f"{year}-01-01"
    
        # Prepare front matter
        print("Preparing front matter...")
        front_matter = {
            'title': title,
            'date': date,
            'authors': [author.strip() for author in pub_data['bib'].get('author', '').split(' and ')],
            'publication_types': ['2'],  # Assuming all are journal articles
            'featured': False,
            'publication': pub_data['bib'].get('journal', ''),
            'abstract': pub_data.get('bib', {}).get('abstract', ''),
            'url_pdf': '',  # You might want to add this manually
            'doi': clean_doi(pub_data),
            'tags': [],
        }
    
        # Create index.md
        with open(os.path.join(folder_path, 'index.md'), 'w', encoding='utf-8') as f:
            f.write('---\n')
            f.write(yaml.dump(front_matter, allow_unicode=True))
            f.write('---\n')
        print(f"Created index.md")
    
        # Create cite.bib if we have citation data
        if 'bib' in pub_data:
            with open(os.path.join(folder_path, 'cite.bib'), 'w', encoding='utf-8') as f:
                # Create BibTeX entry
                bib_entry = f"@article{{{folder_name},\n"
                for key, value in pub_data['bib'].items():
                    if value and key != 'title':  # Skip empty values
                        bib_entry += f"  {key} = {{{value}}},\n"
                bib_entry += "}\n"
                f.write(bib_entry)
            print(f"Created cite.bib")
    except Exception as e:
        print(f"Error processing publication {pub_data['bib'].get('title', 'Unknown')}: {e}")

def main():
    # Your Google Scholar ID
    SCHOLAR_ID = "CceadYwAAAAJ"  # Konstantinos Kougioumoutzis
    
    if not SCHOLAR_ID:
        print("Please set your Google Scholar ID in the script")
        return
    
    # Get the base path (assuming script is in project root/scripts)
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Fetch publications
    publications = get_publications(SCHOLAR_ID)
    
    # Process each publication
    for pub in publications:
        create_publication_folder(pub, base_path)
        print(f"Processed: {pub['bib']['title']}")

if __name__ == "__main__":
    main()
