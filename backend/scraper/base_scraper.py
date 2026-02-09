"""
Base scraper class with rate limiting and robots.txt handling.
"""
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import aiohttp
from bs4 import BeautifulSoup

from backend.core.config import settings


logger = logging.getLogger(__name__)


class BaseScraper:
    """Base scraper with common functionality."""
    
    def __init__(
        self,
        base_url: str,
        delay: float = None,
        respect_robots: bool = None,
        user_agent: str = None,
    ):
        """
        Initialize base scraper.
        
        Args:
            base_url: Base URL of the website to scrape
            delay: Delay between requests in seconds
            respect_robots: Whether to respect robots.txt
            user_agent: User agent string
        """
        self.base_url = base_url
        self.delay = delay or settings.SCRAPER_DELAY
        self.respect_robots = respect_robots if respect_robots is not None else settings.SCRAPER_RESPECT_ROBOTS_TXT
        self.user_agent = user_agent or settings.SCRAPER_USER_AGENT
        
        self.last_request_time = 0
        self.robot_parser = None
        
        if self.respect_robots:
            self._init_robot_parser()
    
    def _init_robot_parser(self):
        """Initialize robots.txt parser."""
        try:
            self.robot_parser = RobotFileParser()
            robots_url = urljoin(self.base_url, '/robots.txt')
            self.robot_parser.set_url(robots_url)
            self.robot_parser.read()
            logger.info(f"Loaded robots.txt from {robots_url}")
        except Exception as e:
            logger.warning(f"Failed to load robots.txt: {e}")
            self.robot_parser = None
    
    def can_fetch(self, url: str) -> bool:
        """
        Check if URL can be fetched according to robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL can be fetched
        """
        if not self.respect_robots or not self.robot_parser:
            return True
        
        try:
            return self.robot_parser.can_fetch(self.user_agent, url)
        except Exception as e:
            logger.warning(f"Error checking robots.txt for {url}: {e}")
            return True
    
    async def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limiting."""
        if self.delay > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.delay:
                wait_time = self.delay - elapsed
                await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    async def fetch_page(self, url: str, session: aiohttp.ClientSession) -> Optional[str]:
        """
        Fetch a page with rate limiting.
        
        Args:
            url: URL to fetch
            session: aiohttp session
            
        Returns:
            HTML content or None if failed
        """
        if not self.can_fetch(url):
            logger.warning(f"URL blocked by robots.txt: {url}")
            return None
        
        await self._wait_for_rate_limit()
        
        headers = {'User-Agent': self.user_agent}
        
        try:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    content = await response.text()
                    logger.info(f"Successfully fetched: {url}")
                    return content
                else:
                    logger.warning(f"Failed to fetch {url}: HTTP {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def parse_html(self, html: str) -> BeautifulSoup:
        """
        Parse HTML content.
        
        Args:
            html: HTML string
            
        Returns:
            BeautifulSoup object
        """
        return BeautifulSoup(html, 'html.parser')
    
    def extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Extract all links from page.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative links
            
        Returns:
            List of absolute URLs
        """
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            absolute_url = urljoin(base_url, href)
            links.append(absolute_url)
        
        return list(set(links))  # Remove duplicates
    
    def is_same_domain(self, url: str) -> bool:
        """
        Check if URL is from the same domain.
        
        Args:
            url: URL to check
            
        Returns:
            True if same domain
        """
        base_domain = urlparse(self.base_url).netloc
        url_domain = urlparse(url).netloc
        return base_domain == url_domain
    
    def clean_text(self, text: str) -> str:
        """
        Clean extracted text.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Remove multiple spaces and newlines
        lines = [line.strip() for line in text.split('\n')]
        lines = [line for line in lines if line]
        return '\n'.join(lines)
