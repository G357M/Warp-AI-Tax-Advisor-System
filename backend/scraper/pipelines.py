"""
Scrapy pipelines for processing scraped documents.
"""
import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models import Document


class DocumentPipeline:
    """Pipeline to save documents to database."""

    def __init__(self):
        self.session: Session = None

    def open_spider(self, spider):
        """Initialize database session when spider opens."""
        self.session = SessionLocal()
        spider.logger.info("DocumentPipeline: Database session opened")

    def close_spider(self, spider):
        """Close database session when spider closes."""
        if self.session:
            self.session.close()
        spider.logger.info("DocumentPipeline: Database session closed")

    def process_item(self, item, spider):
        """
        Process scraped item and save to database.
        
        Args:
            item: Scraped item dictionary
            spider: Spider instance
            
        Returns:
            Processed item
        """
        # Skip non-document items
        if item.get("type") == "discovery":
            return item

        try:
            # Calculate content hash
            content = item.get("content", "")
            if isinstance(content, list):
                content = " ".join(content)
            file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            # Check if document already exists
            existing = (
                self.session.query(Document)
                .filter(Document.source_url == item.get("url"))
                .first()
            )

            if existing:
                # Update if content changed
                if existing.file_hash != file_hash:
                    existing.full_text = content
                    existing.file_hash = file_hash
                    existing.updated_at = datetime.utcnow()
                    self.session.commit()
                    spider.logger.info(f"Updated document: {item.get('url')}")
                else:
                    spider.logger.debug(f"Document unchanged: {item.get('url')}")
            else:
                # Create new document
                document = Document(
                    title=item.get("title", "Unknown"),
                    document_type=item.get("document_type", "unknown"),
                    document_number=item.get("document_number"),
                    language=item.get("language", "ka"),
                    full_text=content,
                    source_url=item.get("url"),
                    file_hash=file_hash,
                )
                self.session.add(document)
                self.session.commit()
                spider.logger.info(f"Saved new document: {item.get('url')}")

        except Exception as e:
            spider.logger.error(f"Error processing item: {e}")
            self.session.rollback()

        return item
