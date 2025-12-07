"""
Scrapy spider for infohub.ge.
"""
import scrapy
from datetime import datetime
from typing import Iterator


class InfoHubSpider(scrapy.Spider):
    """Spider to crawl infohub.ge for tax documents."""

    name = "infohub"
    allowed_domains = ["infohub.ge"]
    start_urls = ["https://infohub.ge/"]

    custom_settings = {
        "DOWNLOAD_DELAY": 2.0,
        "CONCURRENT_REQUESTS": 5,
    }

    def parse(self, response):
        """
        Parse main page and discover document categories.
        
        TODO: Implement actual parsing logic based on infohub.ge structure
        This is a skeleton that needs to be filled in with actual selectors.
        """
        self.logger.info(f"Parsing: {response.url}")

        # TODO: Extract document categories and links
        # Example structure (to be updated based on actual site):
        # for category_link in response.css('div.category a::attr(href)').getall():
        #     yield response.follow(category_link, self.parse_category)

        yield {
            "type": "discovery",
            "url": response.url,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "skeleton_implementation",
        }

    def parse_category(self, response):
        """
        Parse category page and extract document links.
        
        TODO: Implement category parsing
        """
        self.logger.info(f"Parsing category: {response.url}")

        # TODO: Extract document links from category
        # for doc_link in response.css('div.document a::attr(href)').getall():
        #     yield response.follow(doc_link, self.parse_document)

    def parse_document(self, response):
        """
        Parse individual document page.
        
        TODO: Implement document extraction
        """
        self.logger.info(f"Parsing document: {response.url}")

        # TODO: Extract document details
        # Example structure:
        document_data = {
            "url": response.url,
            "title": None,  # response.css('h1::text').get(),
            "document_type": None,
            "document_number": None,
            "date_published": None,
            "language": "ka",
            "content": None,  # response.css('div.content::text').getall(),
            "scraped_at": datetime.utcnow().isoformat(),
        }

        yield document_data
