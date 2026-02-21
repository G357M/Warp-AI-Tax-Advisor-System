#!/usr/bin/env python
"""
Incremental web scraping script for populating vector database.

This script scrapes documents from infohub.rs.ge with:
- State tracking to avoid re-scraping
- Rate limiting to avoid blocking
- Daily incremental updates
- Logging and error handling

Usage:
    python scripts/populate_vector_db.py --max-pages 50 --initial-run
    python scripts/populate_vector_db.py --max-pages 100  # Daily incremental
"""
import sys
import os
import json
import asyncio
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Set

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.infohub_scraper import InfoHubScraper
from rag.vector_store import vector_store
from core.config import settings


# State file location
STATE_FILE = Path(__file__).parent.parent / "data" / "scraper_state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

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


class ScraperState:
    """Manage scraper state for incremental updates."""
    
    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.state = self.load_state()
    
    def load_state(self) -> Dict:
        """Load state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading state: {e}")
        
        # Default state
        return {
            'visited_urls': [],
            'last_run': None,
            'total_documents': 0,
            'total_pages_scraped': 0,
            'runs': []
        }
    
    def save_state(self):
        """Save state to file."""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            logger.info(f"State saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def get_visited_urls(self) -> Set[str]:
        """Get set of visited URLs."""
        return set(self.state.get('visited_urls', []))
    
    def add_visited_url(self, url: str):
        """Add URL to visited set."""
        if 'visited_urls' not in self.state:
            self.state['visited_urls'] = []
        if url not in self.state['visited_urls']:
            self.state['visited_urls'].append(url)
    
    def record_run(self, documents_scraped: int, pages_visited: int):
        """Record scraping run statistics."""
        run_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'documents_scraped': documents_scraped,
            'pages_visited': pages_visited,
        }
        
        if 'runs' not in self.state:
            self.state['runs'] = []
        
        self.state['runs'].append(run_info)
        self.state['last_run'] = run_info['timestamp']
        self.state['total_documents'] += documents_scraped
        self.state['total_pages_scraped'] += pages_visited
        
        # Keep only last 30 runs
        if len(self.state['runs']) > 30:
            self.state['runs'] = self.state['runs'][-30:]


async def run_incremental_scrape(
    start_url: str,
    max_pages: int = 50,
    max_depth: int = 2,
    initial_run: bool = False
):
    """
    Run incremental scraping.
    
    Args:
        start_url: Starting URL (e.g., https://infohub.rs.ge/ka)
        max_pages: Maximum pages to scrape in this run
        max_depth: Maximum link depth to follow
        initial_run: If True, ignore previous state
    """
    logger.info("=" * 80)
    logger.info(f"Starting incremental scrape at {datetime.utcnow().isoformat()}")
    logger.info(f"Start URL: {start_url}")
    logger.info(f"Max pages: {max_pages}, Max depth: {max_depth}")
    logger.info("=" * 80)
    
    # Load state
    state_manager = ScraperState()
    
    if initial_run:
        logger.info("Initial run - starting fresh")
        state_manager.state = {
            'visited_urls': [],
            'last_run': None,
            'total_documents': 0,
            'total_pages_scraped': 0,
            'runs': []
        }
    else:
        visited_count = len(state_manager.state.get('visited_urls', []))
        logger.info(f"Resuming from previous state ({visited_count} URLs visited)")
    
    # Check vector store
    try:
        doc_count = vector_store.get_count()
        logger.info(f"Current vector store count: {doc_count} documents")
    except Exception as e:
        logger.warning(f"Could not get vector store count: {e}")
    
    # Initialize scraper
    scraper = InfoHubScraper()
    
    # Pre-populate visited URLs from state
    if not initial_run:
        scraper.visited_urls = state_manager.get_visited_urls()
        logger.info(f"Loaded {len(scraper.visited_urls)} URLs from state")
    
    # Run scraper
    try:
        result = await scraper.scrape(
            start_url=start_url,
            max_depth=max_depth,
            max_pages=max_pages
        )
        
        # Update state
        for url in scraper.visited_urls:
            state_manager.add_visited_url(url)
        
        state_manager.record_run(
            documents_scraped=result['documents_scraped'],
            pages_visited=result['pages_visited']
        )
        
        state_manager.save_state()
        
        # Log results
        logger.info("=" * 80)
        logger.info("Scraping completed successfully!")
        logger.info(f"Documents scraped this run: {result['documents_scraped']}")
        logger.info(f"Pages visited this run: {result['pages_visited']}")
        logger.info(f"Total documents scraped (all time): {state_manager.state['total_documents']}")
        logger.info(f"Total pages scraped (all time): {state_manager.state['total_pages_scraped']}")
        
        # Check vector store again
        try:
            doc_count_after = vector_store.get_count()
            logger.info(f"Vector store count after scraping: {doc_count_after} documents")
        except Exception as e:
            logger.warning(f"Could not get vector store count: {e}")
        
        logger.info("=" * 80)
        
        return result
        
    except Exception as e:
        logger.error(f"Error during scraping: {e}", exc_info=True)
        state_manager.save_state()  # Save state even on error
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Incremental web scraping for InfoHub vector database"
    )
    parser.add_argument(
        "--start-url",
        default="https://infohub.rs.ge/ka",
        help="Starting URL to scrape (default: https://infohub.rs.ge/ka)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum pages to scrape in this run (default: 50)"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Maximum link depth to follow (default: 2)"
    )
    parser.add_argument(
        "--initial-run",
        action="store_true",
        help="Ignore previous state and start fresh"
    )
    parser.add_argument(
        "--show-state",
        action="store_true",
        help="Show current scraper state and exit"
    )
    
    args = parser.parse_args()
    
    # Show state if requested
    if args.show_state:
        state_manager = ScraperState()
        print(json.dumps(state_manager.state, indent=2, ensure_ascii=False))
        return
    
    # Run scraping
    try:
        result = asyncio.run(run_incremental_scrape(
            start_url=args.start_url,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            initial_run=args.initial_run
        ))
        
        print("\n✅ Scraping completed successfully!")
        print(f"📄 Documents scraped: {result['documents_scraped']}")
        print(f"🔗 Pages visited: {result['pages_visited']}")
        
    except KeyboardInterrupt:
        print("\n⚠️  Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Scraping failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
