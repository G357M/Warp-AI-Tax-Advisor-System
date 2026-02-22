"""
Test InfoHub search API with all document types.
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
            "formats": ["markdown", "links"],
            "waitFor": 3000  # Wait 3 seconds for JavaScript to load
        },
        timeout=60
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None

# Test 1: All document types with skip=0, take=40
print("=" * 80)
print("Test 1: All document types (first 40)")
print("=" * 80)

search_url = "https://infohub.rs.ge/ka/search?types=15&types=16&types=17&skip=0&take=40&searchInName=true&searchInText=true"

result = scrape_url(search_url)

if result and 'data' in result:
    data = result['data']
    markdown = data.get('markdown', '')
    links = data.get('links', [])
    
    print(f"Markdown length: {len(markdown)} chars")
    print(f"Total links: {len(links)}")
    
    doc_links = [link for link in links if '/document/' in link]
    print(f"Document links: {len(doc_links)}")
    
    print(f"\nFirst 1500 chars of content:")
    print("-" * 80)
    print(markdown[:1500])
    print("-" * 80)
    
    if doc_links:
        print(f"\nFirst 5 document links found:")
        for i, link in enumerate(doc_links[:5], 1):
            print(f"{i}. {link}")

# Test 2: Try direct API approach (might be JSON API)
print("\n" + "=" * 80)
print("Test 2: Direct API request (checking if there's JSON API)")
print("=" * 80)

api_url = "https://infohub.rs.ge/api/search"
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json"
}

payload = {
    "types": [15, 16, 17],  # First few types
    "skip": 0,
    "take": 40,
    "searchInName": True,
    "searchInText": True
}

try:
    response = requests.post(api_url, json=payload, headers=headers, timeout=30)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        json_data = response.json()
        print(f"Response keys: {json_data.keys() if isinstance(json_data, dict) else 'Not a dict'}")
        print(f"Response preview:")
        print(json.dumps(json_data, indent=2, ensure_ascii=False)[:1000])
    else:
        print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 80)
