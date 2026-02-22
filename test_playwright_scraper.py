"""
Test Playwright scraper for InfoHub.
"""
import asyncio
import sys
import os
import logging

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Set environment variables
os.environ['DATABASE_URL'] = 'postgresql://infohub:infohub123@46.224.145.5:5432/infohub_db'
os.environ['REDIS_URL'] = 'redis://46.224.145.5:6379/0'
os.environ['SECRET_KEY'] = 'test-key'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-key'

from scraper.playwright_scraper import PlaywrightInfoHubScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 80)
    logger.info("Testing Playwright InfoHub Scraper")
    logger.info("=" * 80)
    
    scraper = PlaywrightInfoHubScraper()
    
    try:
        # Initialize browser
        await scraper.init_browser()
        
        # Scrape key documents
        logger.info("\nScraping key tax documents...")
        results = await scraper.scrape_key_documents()
        
        # Print results
        logger.info("\n" + "=" * 80)
        logger.info("RESULTS")
        logger.info("=" * 80)
        
        for key, data in results.items():
            logger.info(f"\n{key.upper()}:")
            logger.info(f"  Query: {data['query']}")
            logger.info(f"  Documents found: {data['documents_found']}")
            
            if data['documents']:
                logger.info("  Documents:")
                for doc in data['documents']:
                    logger.info(f"    - {doc['title']}")
                    logger.info(f"      URL: {doc['url']}")
        
        logger.info(f"\nTotal documents scraped: {scraper.documents_scraped}")
    
    finally:
        # Close browser
        await scraper.close_browser()
    
    logger.info("\n" + "=" * 80)
    logger.info("Test complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
