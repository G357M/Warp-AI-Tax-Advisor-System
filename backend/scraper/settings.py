"""
Scrapy settings for InfoHub spider.
"""
from backend.core.config import settings


BOT_NAME = "infohub_scraper"

SPIDER_MODULES = ["backend.scraper.spiders"]
NEWSPIDER_MODULE = "backend.scraper.spiders"

# Crawl responsibly
ROBOTSTXT_OBEY = settings.SCRAPER_RESPECT_ROBOTS_TXT
USER_AGENT = settings.SCRAPER_USER_AGENT

# Configure maximum concurrent requests
CONCURRENT_REQUESTS = settings.SCRAPER_CONCURRENT_REQUESTS
DOWNLOAD_DELAY = settings.SCRAPER_DELAY

# Enable autothrottle
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

# Disable cookies
COOKIES_ENABLED = False

# Request headers
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ka,en;q=0.9,ru;q=0.8",
}

# Item pipelines
ITEM_PIPELINES = {
    "backend.scraper.pipelines.DocumentPipeline": 300,
}

# Retry settings
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# Logging
LOG_LEVEL = settings.LOG_LEVEL
