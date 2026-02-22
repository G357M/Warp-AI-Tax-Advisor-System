"""
Run enhanced priority-based scraper to collect relevant legislative documents.
"""
import asyncio
import sys
import os
import logging

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scraper.enhanced_scraper import EnhancedInfoHubScraper
from core.config import settings


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('priority_scraper.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Run priority-based scraping."""
    logger.info("=" * 80)
    logger.info("Starting Enhanced InfoHub Priority Scraper")
    logger.info("=" * 80)
    
    # Initialize scraper
    api_key = "fc-77900ef0e837476985d88650596d0ec7"  # Firecrawl API key
    scraper = EnhancedInfoHubScraper(api_key)
    
    # Run scraping with priorities
    result = await scraper.scrape_priority_documents(
        base_url="https://infohub.rs.ge/ka",
        high_priority_limit=50,  # Laws, Orders - most important
        medium_priority_limit=30,  # Guidelines, methodologies
        low_priority_limit=10,  # Case law
    )
    
    # Print results
    logger.info("=" * 80)
    logger.info("SCRAPING SUMMARY")
    logger.info("=" * 80)
    
    logger.info(f"\nKey Documents Found: {len(result['key_documents'])}")
    for doc in result['key_documents']:
        logger.info(f"  ✓ {doc['key']}: {doc['title']}")
    
    stats = result['statistics']
    logger.info(f"\nTotal Documents Scraped: {stats['total']}")
    logger.info(f"  High Priority: {stats['by_priority']['high']}")
    logger.info(f"  Medium Priority: {stats['by_priority']['medium']}")
    logger.info(f"  Low Priority: {stats['by_priority']['low']}")
    
    logger.info(f"\nBy Document Type:")
    for doc_type, count in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
        logger.info(f"  {doc_type}: {count}")
    
    logger.info("\n" + "=" * 80)
    logger.info("Scraping complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
