"""
Fetch and analyze the Tax Code document found by search.
"""
import requests

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
            "formats": ["markdown"]
        },
        timeout=60
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None

# Document found from search
doc_url = "https://infohub.rs.ge/ka/workspace/document/0fe44fbf-2372-448e-a46e-c310b1611129"

print("Fetching Tax Code document...")
print(f"URL: {doc_url}\n")

result = scrape_url(doc_url)

if result and 'data' in result:
    markdown = result['data'].get('markdown', '')
    
    print(f"Document length: {len(markdown)} characters")
    print(f"Document preview (first 1000 chars):\n")
    print("=" * 80)
    print(markdown[:1000])
    print("=" * 80)
    
    # Check if it's the Tax Code
    if 'საგადასახადო კოდექსი' in markdown or 'Tax Code' in markdown or 'დღგ' in markdown:
        print("\n✓ This appears to be a tax-related document")
    else:
        print("\n✗ May not be the Tax Code")
    
    # Save to file
    with open('tax_code_sample.md', 'w', encoding='utf-8') as f:
        f.write(markdown)
    print(f"\nFull document saved to: tax_code_sample.md ({len(markdown)} chars)")
else:
    print("Failed to fetch document")
