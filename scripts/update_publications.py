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

def get_publications(scholar_id):
    """Fetch publications from Google Scholar."""
    # Optional: Use proxies if you hit rate limits
    # pg = ProxyGenerator()
    # pg.FreeProxies()
    # scholarly.use_proxy(pg)
    
    try:
        # Search for the author by ID
        author = scholarly.search_author_id(scholar_id)
        if not author:
            print(f"No author found with ID: {scholar_id}")
            return []
            
        # Fill in author details including publications
        author = scholarly.fill(author)
        publications = scholarly.fill(author['publications'])
        
        return publications
    except Exception as e:
        print(f"Error fetching publications: {e}")
        return []

def create_publication_folder(pub_data, base_path):
    """Create a publication folder with index.md and cite.bib files."""
    # Create folder name from title
    folder_name = sanitize_filename(pub_data['bib']['title'])
    folder_path = os.path.join(base_path, 'content/publication', folder_name)
    
    # Create folder if it doesn't exist
    os.makedirs(folder_path, exist_ok=True)
    
    # Prepare front matter
    front_matter = {
        'title': pub_data['bib']['title'],
        'date': pub_data['bib'].get('pub_year', ''),
        'authors': [author.strip() for author in pub_data['bib'].get('author', '').split(' and ')],
        'publication_types': ['2'],  # Assuming all are journal articles
        'featured': False,
        'publication': pub_data['bib'].get('journal', ''),
        'abstract': pub_data.get('bib', {}).get('abstract', ''),
        'url_pdf': '',  # You might want to add this manually
        'doi': pub_data.get('doi', ''),
        'tags': [],
    }
    
    # Create index.md
    with open(os.path.join(folder_path, 'index.md'), 'w', encoding='utf-8') as f:
        f.write('---\n')
        f.write(yaml.dump(front_matter, allow_unicode=True))
        f.write('---\n')
    
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

def main():
    # Your Google Scholar ID
    SCHOLAR_ID = ""  # Add your Google Scholar ID here
    
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
