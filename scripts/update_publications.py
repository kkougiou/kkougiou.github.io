#!/usr/bin/env python3
import os
import json
from datetime import datetime
from scholarly import scholarly, ProxyGenerator
import yaml
import re

def sanitize_filename(title):
    """Convert title to filename-friendly format."""
    # Remove special characters and convert to lowercase
    filename = re.sub(r'[^a-zA-Z0-9\s-]', '', title.lower())
    # Replace spaces with hyphens
    filename = re.sub(r'\s+', '-', filename.strip())
    return filename

def parse_year(year_str):
    """Parse year from various formats and validate."""
    if not year_str:
        return str(datetime.now().year)
    
    try:
        # Try to convert to integer
        year = int(year_str)
        # Validate year is reasonable (between 1900 and current year)
        current_year = datetime.now().year
        if year < 1900 or year > current_year:
            return str(current_year)
        return str(year)
    except (ValueError, TypeError):
        # If conversion fails, return current year
        return str(datetime.now().year)

def clean_doi(doi):
    """Clean DOI by removing common prefixes."""
    if not doi:
        return ''
    # Remove common prefixes
    prefixes = ['https://doi.org/', 'http://doi.org/', 'doi.org/']
    for prefix in prefixes:
        if doi.startswith(prefix):
            return doi[len(prefix):]
    return doi

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
    
        # Prepare front matter
        print("Preparing front matter...")
        front_matter = {
            'title': title,
            'date': parse_year(pub_data['bib'].get('pub_year', '')),
            'authors': [author.strip() for author in pub_data['bib'].get('author', '').split(' and ')],
            'publication_types': ['2'],  # Assuming all are journal articles
            'featured': False,
            'publication': pub_data['bib'].get('journal', ''),
            'abstract': pub_data.get('bib', {}).get('abstract', ''),
            'url_pdf': '',  # You might want to add this manually
            'doi': clean_doi(pub_data.get('pub_url', '')),
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
