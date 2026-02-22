"""
Simplified Playwright test - just scrape and print results.
No database or vector store dependencies.
"""
import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def scrape_search(search_query: str):
    """Scrape InfoHub search results."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Go to search page
        search_url = f"https://infohub.rs.ge/ka/search?searchText={search_query}&skip=0&take=40"
        logger.info(f"Searching: {search_url}")
        
        await page.goto(search_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)  # Wait for content to load
        
        # Extract document links
        links = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a'));
                return links
                    .map(a => a.href)
                    .filter(href => href && href.includes('/document/'));
            }
        """)
        
        unique_links = list(set(links))
        logger.info(f"Found {len(unique_links)} unique document links")
        
        # Try to scrape first document
        if unique_links:
            doc_url = unique_links[0]
            logger.info(f"\nScraping first document: {doc_url}")
            
            await page.goto(doc_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            
            # Extract document data
            doc_data = await page.evaluate("""
                () => {
                    const titleEl = document.querySelector('h1, .document-title, .title');
                    const title = titleEl ? titleEl.innerText : 'Untitled';
                    
                    const contentEl = document.querySelector('.document-content, .content, main, article') || document.body;
                    const content = contentEl.innerText;
                    
                    return {
                        title,
                        content,
                        contentLength: content.length
                    };
                }
            """)
            
            logger.info(f"\nDocument title: {doc_data['title']}")
            logger.info(f"Content length: {doc_data['contentLength']} chars")
            logger.info(f"\nFirst 500 chars:")
            logger.info("-" * 80)
            logger.info(doc_data['content'][:500])
            logger.info("-" * 80)
            
            # Check if it's tax-related
            content_lower = doc_data['content'].lower()
            if 'დღგ' in doc_data['content'] or 'საგადასახადო' in doc_data['content']:
                logger.info("\n✓ This is a tax-related document!")
            else:
                logger.info("\n✗ Not clearly tax-related")
            
            return {
                'search_query': search_query,
                'documents_found': len(unique_links),
                'first_document': doc_data
            }
        
        await browser.close()
        
        return {
            'search_query': search_query,
            'documents_found': len(unique_links),
            'first_document': None
        }


async def main():
    logger.info("=" * 80)
    logger.info("Playwright InfoHub Test (Simplified)")
    logger.info("=" * 80)
    
    # Test searches
    searches = [
        'საგადასახადო კოდექსი',  # Tax Code
        'ბრძანება 996',          # Order 996
        'დღგ',                    # VAT
    ]
    
    results = {}
    
    for query in searches:
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Testing query: {query}")
        logger.info('=' * 80)
        
        result = await scrape_search(query)
        results[query] = result
        
        await asyncio.sleep(2)  # Rate limiting
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    
    for query, data in results.items():
        logger.info(f"\nQuery: {query}")
        logger.info(f"  Documents found: {data['documents_found']}")
        if data['first_document']:
            logger.info(f"  First doc title: {data['first_document']['title']}")
            logger.info(f"  First doc length: {data['first_document']['contentLength']} chars")


if __name__ == "__main__":
    asyncio.run(main())
