"""
Simple test of Firecrawl scraper without full backend dependencies.
Tests document type filtering on InfoHub.
"""
import requests
import json

FIRECRAWL_API_KEY = "fc-77900ef0e837476985d88650596d0ec7"
FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v2"

def scrape_url(url):
    """Scrape a URL using Firecrawl API."""
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(
        f"{FIRECRAWL_BASE_URL}/scrape",
        headers=headers,
        json={
            "url": url,
            "formats": ["markdown", "links"]
        },
        timeout=60
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None

def main():
    print("=" * 80)
    print("Testing InfoHub Document Type Scraping")
    print("=" * 80)
    
    # Test 1: Search for Tax Code
    print("\n1. Searching for საგადასახადო კოდექსი (Tax Code)...")
    tax_code_url = "https://infohub.rs.ge/ka?search=საგადასახადო კოდექსი"
    result = scrape_url(tax_code_url)
    
    if result and 'data' in result:
        data = result['data']
        links = data.get('links', [])
        doc_links = [link for link in links if '/document/' in link]
        print(f"   Found {len(doc_links)} document links")
        if doc_links:
            print(f"   First result: {doc_links[0]}")
    
    # Test 2: Search for Order 996
    print("\n2. Searching for ბრძანება 996 (Order 996)...")
    order_996_url = "https://infohub.rs.ge/ka?search=ბრძანება 996"
    result = scrape_url(order_996_url)
    
    if result and 'data' in result:
        data = result['data']
        links = data.get('links', [])
        doc_links = [link for link in links if '/document/' in link]
        print(f"   Found {len(doc_links)} document links")
        if doc_links:
            print(f"   First result: {doc_links[0]}")
    
    # Test 3: Try document type filter
    print("\n3. Testing document type filter (საქართველოს კანონი - Laws)...")
    law_url = "https://infohub.rs.ge/ka?documentType=საქართველოს კანონი"
    result = scrape_url(law_url)
    
    if result and 'data' in result:
        data = result['data']
        markdown = data.get('markdown', '')
        links = data.get('links', [])
        print(f"   Page content length: {len(markdown)} chars")
        print(f"   Total links found: {len(links)}")
        doc_links = [link for link in links if '/document/' in link]
        print(f"   Document links: {len(doc_links)}")
    
    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()
