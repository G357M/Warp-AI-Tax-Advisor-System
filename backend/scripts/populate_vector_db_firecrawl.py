#!/usr/bin/env python
"""
Firecrawl-based scraping script for InfoHub SPA site.

Usage:
    python scripts/populate_vector_db_firecrawl.py --max-pages-per-section 5
    python scripts/populate_vector_db_firecrawl.py --section NewDocument --max-pages 10
"""
import sys
import os
import asyncio
import logging
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.firecrawl_scraper import FirecrawlScraper
from rag.vector_store import vector_store
from core.config import settings


# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Firecrawl-based scraping for InfoHub SPA site"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("FIRECRAWL_API_KEY", "fc-77900ef0e837476985d88650596d0ec7"),
        help="Firecrawl API key (default: from FIRECRAWL_API_KEY env var)"
    )
    parser.add_argument(
        "--section",
        choices=["NewDocument", "LegislativeNews", "Bill", "all"],
        default="all",
        help="Which section to scrape (default: all)"
    )
    parser.add_argument(
        "--max-pages-per-section",
        type=int,
        default=5,
        help="Maximum pages to scrape per section (default: 5)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum pages for single section (overrides --max-pages-per-section)"
    )
    
    args = parser.parse_args()
    
    # Initialize scraper
    logger.info("=" * 80)
    logger.info("Starting Firecrawl scraping")
    logger.info(f"API Key: {args.api_key[:10]}...")
    logger.info("=" * 80)
    
    # Check vector store
    try:
        doc_count = vector_store.get_count()
        logger.info(f"Current vector store count: {doc_count} documents")
    except Exception as e:
        logger.warning(f"Could not get vector store count: {e}")
    
    scraper = FirecrawlScraper(api_key=args.api_key)
    
    try:
        if args.section == "all":
            # Scrape all sections
            max_pages = args.max_pages or args.max_pages_per_section
            result = await scraper.scrape_all_sections(
                base_url="https://infohub.rs.ge/ka",
                max_pages_per_section=max_pages
            )
        else:
            # Scrape single section
            max_pages = args.max_pages or args.max_pages_per_section
            
            from core.database import SessionLocal
            db = SessionLocal()
            
            try:
                documents = await scraper.scrape_paginated_section(
                    base_url="https://infohub.rs.ge/ka",
                    species=args.section,
                    max_pages=max_pages,
                    db=db
                )
                
                result = {
                    'documents_scraped': len(documents),
                    'pages_scraped': scraper.pages_scraped,
                    'documents': [{'id': doc.id, 'title': doc.title, 'url': doc.url} for doc in documents],
                }
            finally:
                db.close()
        
        # Log results
        logger.info("=" * 80)
        logger.info("Scraping completed successfully!")
        logger.info(f"Documents scraped: {result['documents_scraped']}")
        logger.info(f"Pages scraped: {result['pages_scraped']}")
        
        # Check vector store again
        try:
            doc_count_after = vector_store.get_count()
            logger.info(f"Vector store count after scraping: {doc_count_after} documents")
        except Exception as e:
            logger.warning(f"Could not get vector store count: {e}")
        
        logger.info("=" * 80)
        
        print("\n✅ Scraping completed successfully!")
        print(f"📄 Documents scraped: {result['documents_scraped']}")
        print(f"🔗 Pages scraped: {result['pages_scraped']}")
        
        # Show first few documents
        if result['documents']:
            print("\nFirst documents:")
            for doc in result['documents'][:5]:
                print(f"  - {doc['title'][:60]}...")
        
    except KeyboardInterrupt:
        print("\n⚠️  Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Scraping failed: {e}", exc_info=True)
        print(f"\n❌ Scraping failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
