"""
InfoHub.ge scraper for tax documents.
"""
import asyncio
import logging
import re
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from urllib.parse import urlparse, urljoin
import aiohttp
from sqlalchemy.orm import Session

from backend.scraper.base_scraper import BaseScraper
from backend.core.database import SessionLocal
from backend.models.document import Document, DocumentChunk
from backend.rag.embeddings import embeddings_generator
from backend.rag.vector_store import vector_store
from backend.core.config import settings


logger = logging.getLogger(__name__)


class InfoHubScraper(BaseScraper):
    """Scraper for infohub.ge tax documents."""
    
    def __init__(self):
        super().__init__(base_url="https://infohub.ge")
        self.visited_urls = set()
        self.documents_scraped = 0
    
    def detect_language(self, text: str) -> str:
        """
        Detect language of text (Georgian, Russian, or English).
        
        Args:
            text: Text to analyze
            
        Returns:
            Language code: 'ka', 'ru', or 'en'
        """
        # Georgian characters
        if re.search(r'[\u10A0-\u10FF]', text):
            return 'ka'
        
        # Cyrillic characters (Russian)
        if re.search(r'[\u0400-\u04FF]', text):
            return 'ru'
        
        # Default to English
        return 'en'
    
    def extract_document_metadata(self, soup, url: str) -> Dict:
        """
        Extract metadata from document page.
        
        Args:
            soup: BeautifulSoup object
            url: Document URL
            
        Returns:
            Dictionary with metadata
        """
        metadata = {
            'url': url,
            'source': 'infohub.ge',
            'scraped_at': datetime.utcnow().isoformat(),
        }
        
        # Try to extract title
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            metadata['title'] = self.clean_text(title_tag.get_text())
        
        # Try to extract date
        date_patterns = [
            r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',
            r'(\d{4}[./-]\d{1,2}[./-]\d{1,2})',
        ]
        page_text = soup.get_text()
        for pattern in date_patterns:
            match = re.search(pattern, page_text)
            if match:
                metadata['date'] = match.group(1)
                break
        
        # Extract document type/category from URL or content
        if '/tax/' in url or 'налог' in page_text.lower() or 'საგადასახადო' in page_text:
            metadata['category'] = 'tax'
        elif '/vat/' in url or 'ндс' in page_text.lower() or 'დღგ' in page_text:
            metadata['category'] = 'vat'
        elif '/corporate/' in url or 'корпоратив' in page_text.lower():
            metadata['category'] = 'corporate'
        
        return metadata
    
    def extract_main_content(self, soup) -> str:
        """
        Extract main text content from page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Extracted text
        """
        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            script.decompose()
        
        # Try to find main content area
        content = None
        for selector in ['article', 'main', '.content', '#content', '.post-content']:
            content = soup.select_one(selector)
            if content:
                break
        
        # Fall back to body if no main content found
        if not content:
            content = soup.find('body')
        
        if content:
            text = content.get_text(separator='\n')
            return self.clean_text(text)
        
        return ""
    
    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """
        Split text into chunks for RAG.
        
        Args:
            text: Text to chunk
            chunk_size: Maximum chunk size in characters
            overlap: Overlap between chunks
            
        Returns:
            List of text chunks
        """
        chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        overlap = overlap or settings.RAG_CHUNK_OVERLAP
        
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence endings
                for i in range(end, max(start + overlap, start), -1):
                    if text[i] in '.!?\n':
                        end = i + 1
                        break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - overlap
        
        return chunks
    
    async def process_document(
        self,
        url: str,
        html: str,
        db: Session
    ) -> Optional[Document]:
        """
        Process and store a document.
        
        Args:
            url: Document URL
            html: HTML content
            db: Database session
            
        Returns:
            Stored Document object or None
        """
        try:
            soup = self.parse_html(html)
            
            # Extract content and metadata
            text = self.extract_main_content(soup)
            if not text or len(text) < 100:  # Skip if too short
                logger.info(f"Skipping {url}: content too short")
                return None
            
            metadata = self.extract_document_metadata(soup, url)
            language = self.detect_language(text)
            metadata['language'] = language
            
            # Create document hash for deduplication
            content_hash = hashlib.md5(text.encode()).hexdigest()
            
            # Check if already exists
            existing = db.query(Document).filter_by(url=url).first()
            if existing:
                logger.info(f"Document already exists: {url}")
                return existing
            
            # Create document record
            document = Document(
                url=url,
                title=metadata.get('title', 'Untitled'),
                content=text,
                language=language,
                source='infohub.ge',
                metadata_=metadata,
                content_hash=content_hash,
            )
            db.add(document)
            db.flush()  # Get document ID
            
            # Chunk text
            chunks = self.chunk_text(text)
            logger.info(f"Created {len(chunks)} chunks for document {document.id}")
            
            # Generate embeddings
            if embeddings_generator.model:
                embeddings = embeddings_generator.encode(chunks)
                
                # Store chunks in database and vector store
                vector_ids = []
                vector_embeddings = []
                vector_metadatas = []
                vector_documents = []
                
                for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                    # Create chunk record
                    chunk = DocumentChunk(
                        document_id=document.id,
                        chunk_index=i,
                        content=chunk_text,
                        metadata_={'position': i, 'total_chunks': len(chunks)},
                    )
                    db.add(chunk)
                    db.flush()
                    
                    # Prepare for vector store
                    vector_ids.append(f"doc_{document.id}_chunk_{chunk.id}")
                    vector_embeddings.append(embedding)
                    vector_metadatas.append({
                        'document_id': document.id,
                        'chunk_id': chunk.id,
                        'title': document.title,
                        'url': document.url,
                        'language': language,
                        'source': 'infohub.ge',
                        'chunk_index': i,
                    })
                    vector_documents.append(chunk_text)
                
                # Add to vector store
                if vector_store.client:
                    vector_store.add_documents(
                        ids=vector_ids,
                        embeddings=vector_embeddings,
                        documents=vector_documents,
                        metadatas=vector_metadatas,
                    )
                    logger.info(f"Added {len(vector_ids)} chunks to vector store")
            
            db.commit()
            self.documents_scraped += 1
            logger.info(f"Successfully processed document: {url}")
            
            return document
            
        except Exception as e:
            logger.error(f"Error processing document {url}: {e}")
            db.rollback()
            return None
    
    async def scrape_page(
        self,
        url: str,
        session: aiohttp.ClientSession,
        db: Session,
        max_depth: int = 2,
        current_depth: int = 0,
    ) -> List[Document]:
        """
        Scrape a page and optionally follow links.
        
        Args:
            url: URL to scrape
            session: aiohttp session
            db: Database session
            max_depth: Maximum depth to follow links
            current_depth: Current depth
            
        Returns:
            List of processed documents
        """
        if url in self.visited_urls or not self.is_same_domain(url):
            return []
        
        self.visited_urls.add(url)
        logger.info(f"Scraping {url} (depth {current_depth})")
        
        documents = []
        
        # Fetch page
        html = await self.fetch_page(url, session)
        if not html:
            return documents
        
        # Process current page
        document = await self.process_document(url, html, db)
        if document:
            documents.append(document)
        
        # Follow links if not at max depth
        if current_depth < max_depth:
            soup = self.parse_html(html)
            links = self.extract_links(soup, url)
            
            # Filter relevant links (e.g., tax-related pages)
            relevant_keywords = ['tax', 'налог', 'vat', 'ндс', 'საგადასახადო', 'დღგ', 'law', 'закон', 'კანონი']
            relevant_links = [
                link for link in links
                if any(keyword in link.lower() for keyword in relevant_keywords)
                and self.is_same_domain(link)
                and link not in self.visited_urls
            ]
            
            # Scrape linked pages
            for link in relevant_links[:10]:  # Limit to 10 links per page
                child_documents = await self.scrape_page(
                    link, session, db, max_depth, current_depth + 1
                )
                documents.extend(child_documents)
        
        return documents
    
    async def scrape(
        self,
        start_url: str,
        max_depth: int = 2,
        max_pages: int = 100,
    ) -> Dict:
        """
        Start scraping from a URL.
        
        Args:
            start_url: Starting URL
            max_depth: Maximum link depth to follow
            max_pages: Maximum number of pages to scrape
            
        Returns:
            Dictionary with scraping results
        """
        self.visited_urls = set()
        self.documents_scraped = 0
        
        db = SessionLocal()
        documents = []
        
        try:
            async with aiohttp.ClientSession() as session:
                documents = await self.scrape_page(
                    start_url, session, db, max_depth=max_depth
                )
                
                # Limit total pages
                if len(self.visited_urls) >= max_pages:
                    logger.warning(f"Reached max pages limit: {max_pages}")
        
        finally:
            db.close()
        
        return {
            'documents_scraped': self.documents_scraped,
            'pages_visited': len(self.visited_urls),
            'documents': [{'id': doc.id, 'title': doc.title, 'url': doc.url} for doc in documents],
        }
