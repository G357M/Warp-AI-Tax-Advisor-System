"""
InfoHub scraper for tax/legal documents from infohub.rs.ge.
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

from scraper.base_scraper import BaseScraper
from core.database import SessionLocal
from models.document import Document, DocumentChunk
from rag.embeddings import embeddings_generator
from rag.vector_store_pgvector import vector_store
from core.config import settings


logger = logging.getLogger(__name__)


class InfoHubScraper(BaseScraper):
    """Scraper for infohub.rs.ge tax documents."""
    
    def __init__(self):
        super().__init__(base_url="https://infohub.rs.ge")
        self.visited_urls = set()
        self.documents_scraped = 0
    
    def detect_language(self, text: str) -> str:
        if re.search(r'[\u10A0-\u10FF]', text):
            return 'ka'
        if re.search(r'[\u0400-\u04FF]', text):
            return 'ru'
        return 'en'
    
    def extract_document_metadata(self, soup, url: str) -> Dict:
        metadata = {
            'url': url,
            'source': 'infohub.rs.ge',
            'scraped_at': datetime.utcnow().isoformat(),
        }
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            metadata['title'] = self.clean_text(title_tag.get_text())
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
        if '/tax/' in url or 'налог' in page_text.lower() or 'საგადასახადო' in page_text:
            metadata['category'] = 'tax'
        elif '/vat/' in url or 'ндс' in page_text.lower() or 'დღგ' in page_text:
            metadata['category'] = 'vat'
        elif '/corporate/' in url or 'корпоратив' in page_text.lower():
            metadata['category'] = 'corporate'
        return metadata
    
    def extract_main_content(self, soup) -> str:
        for script in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            script.decompose()
        content = None
        for selector in ['article', 'main', '.content', '#content', '.post-content']:
            content = soup.select_one(selector)
            if content:
                break
        if not content:
            content = soup.find('body')
        if content:
            text = content.get_text(separator='\n')
            return self.clean_text(text)
        return ""
    
    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        overlap = overlap or settings.RAG_CHUNK_OVERLAP
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end < len(text):
                for i in range(end, max(start + overlap, start), -1):
                    if text[i] in '.!?\n':
                        end = i + 1
                        break
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - overlap
        return chunks
    
    async def process_document(self, url: str, html: str, db: Session) -> Optional[Document]:
        try:
            soup = self.parse_html(html)
            text = self.extract_main_content(soup)
            if not text or len(text) < 100:
                logger.info(f"Skipping {url}: content too short")
                return None
            metadata = self.extract_document_metadata(soup, url)
            language = self.detect_language(text)
            metadata['language'] = language
            content_hash = hashlib.md5(text.encode()).hexdigest()
            existing = db.query(Document).filter_by(source_url=url).first()
            if existing:
                logger.info(f"Document already exists: {url}")
                return existing
            document = Document(
                source_url=url,
                title=metadata.get('title', 'Untitled'),
                document_type='guideline',
                full_text=text,
                language=language,
                metadata_json=metadata,
                file_hash=content_hash,
            )
            db.add(document)
            db.flush()
            chunks = self.chunk_text(text)
            logger.info(f"Created {len(chunks)} chunks for document {document.id}")
            if embeddings_generator.model:
                embeddings = embeddings_generator.encode(chunks)
                vector_ids = []
                vector_embeddings = []
                vector_metadatas = []
                vector_documents = []
                for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                    chunk = DocumentChunk(
                        document_id=document.id,
                        chunk_index=i,
                        content=chunk_text,
                        metadata_json={'position': i, 'total_chunks': len(chunks)},
                    )
                    db.add(chunk)
                    db.flush()
                    vector_ids.append(f"doc_{document.id}_chunk_{chunk.id}")
                    vector_embeddings.append(embedding)
                    vector_metadatas.append({
                        'document_id': document.id,
                        'chunk_id': chunk.id,
                        'title': document.title,
                        'url': document.source_url,
                        'language': language,
                        'source': 'infohub.rs.ge',
                        'chunk_index': i,
                    })
                    vector_documents.append(chunk_text)
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
    
    async def scrape_page(self, url: str, session: aiohttp.ClientSession, db: Session, max_depth: int = 2, current_depth: int = 0) -> List[Document]:
        if url in self.visited_urls or not self.is_same_domain(url):
            return []
        self.visited_urls.add(url)
        logger.info(f"Scraping {url} (depth {current_depth})")
        documents = []
        html = await self.fetch_page(url, session)
        if not html:
            return documents
        document = await self.process_document(url, html, db)
        if document:
            documents.append(document)
        if current_depth < max_depth:
            soup = self.parse_html(html)
            links = self.extract_links(soup, url)
            relevant_keywords = ['tax', 'налог', 'vat', 'ндс', 'საგადასახადო', 'დღგ', 'law', 'закон', 'კანონი']
            relevant_links = [
                link for link in links
                if any(keyword in link.lower() for keyword in relevant_keywords)
                and self.is_same_domain(link)
                and link not in self.visited_urls
            ]
            for link in relevant_links[:10]:
                child_documents = await self.scrape_page(link, session, db, max_depth, current_depth + 1)
                documents.extend(child_documents)
        return documents
    
    async def scrape(self, start_url: str, max_depth: int = 2, max_pages: int = 100) -> Dict:
        self.visited_urls = set()
        self.documents_scraped = 0
        db = SessionLocal()
        documents = []
        try:
            async with aiohttp.ClientSession() as session:
                documents = await self.scrape_page(start_url, session, db, max_depth=max_depth)
                if len(self.visited_urls) >= max_pages:
                    logger.warning(f"Reached max pages limit: {max_pages}")
        finally:
            db.close()
        return {
            'documents_scraped': self.documents_scraped,
            'pages_visited': len(self.visited_urls),
            'documents': [{'id': doc.id, 'title': doc.title, 'url': doc.source_url} for doc in documents],
        }
