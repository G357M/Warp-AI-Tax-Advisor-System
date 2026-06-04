"""
Explore infohub.rs.ge structure to find all document categories.
"""
import requests
import json
import os

FIRECRAWL_API_KEY = os.environ["FIRECRAWL_API_KEY"]
BASE_URL = "https://api.firecrawl.dev/v2/scrape"

def scrape_page(url):
    """Scrape a page using Firecrawl."""
    try:
        response = requests.post(
            BASE_URL,
            headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}"},
            json={"url": url, "formats": ["markdown", "links"]},
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def main():
    print("Exploring infohub.rs.ge structure...")
    
    # Scrape main page to find categories
    main_page_url = "https://infohub.rs.ge/ka"
    result = scrape_page(main_page_url)
    
    if not result:
        print("Failed to scrape main page")
        return
    
    data = result.get("data", {})
    markdown = data.get("markdown", "")
    links = data.get("links", [])
    
    # Save raw data
    with open("infohub_main_page.md", "w", encoding="utf-8") as f:
        f.write(markdown)
    
    with open("infohub_links.json", "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)
    
    print(f"✓ Saved main page content")
    print(f"✓ Found {len(links)} links")
    
    # Filter links for document categories
    species_links = []
    for link in links:
        if "species=" in link or "workspace" in link:
            species_links.append(link)
    
    print(f"\n📋 Found {len(species_links)} potential category links:")
    for link in species_links[:20]:
        print(f"  - {link}")
    
    # Try to extract species types from links
    species_types = set()
    for link in links:
        if "species=" in link:
            parts = link.split("species=")
            if len(parts) > 1:
                species = parts[1].split("&")[0]
                species_types.add(species)
    
    print(f"\n🎯 Discovered species types:")
    for species in sorted(species_types):
        print(f"  - {species}")
    
    # Save species types
    with open("infohub_species.json", "w", encoding="utf-8") as f:
        json.dump(list(species_types), f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Saved to infohub_species.json")

if __name__ == "__main__":
    main()
