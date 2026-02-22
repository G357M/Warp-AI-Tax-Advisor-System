"""
Playwright-based scraper for InfoHub (JavaScript-rendered SPA).
"""
import asyncio
import logging
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser
import hashlib
from datetime import datetime

from core.database import SessionLocal
from models.document import Document, DocumentChunk
from rag.embeddings import embeddings_generator
from rag.vector_store import vector_store
from core.config import settings


logger = logging.getLogger(__name__)


class PlaywrightInfoHubScraper:
    """Scraper using Playwright for JavaScript-rendered content."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.documents_scraped = 0
    
    async def init_browser(self):
        """Initialize Playwright browser."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        logger.info("Browser initialized")
    
    async def close_browser(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
            logger.info("Browser closed")
    
    async def scrape_search_page(
        self,
        page: Page,
        search_url: str,
        wait_selector: str = ".document-item, .search-result, article"
    ) -> Dict:
        """
        Scrape a search results page.
        
        Returns:
            Dict with document links and metadata
        """
        try:
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            
            # Wait for content to load
            try:
                await page.wait_for_selector(wait_selector, timeout=10000)
            except:
                logger.warning(f"Selector {wait_selector} not found, continuing...")
            
            # Additional wait for dynamic content
            await asyncio.sleep(2)
            
            # Get all links
            links = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a'));
                    return links
                        .map(a => a.href)
                        .filter(href => href && href.includes('/document/'));
                }
            """)
            
            # Get page text for analysis
            text_content = await page.evaluate("() => document.body.innerText")
            
            return {
                'links': links,
                'text_content': text_content,
                'unique_docs': list(set(links))
            }
        
        except Exception as e:
            logger.error(f"Error scraping search page {search_url}: {e}")
            return {'links': [], 'text_content': '', 'unique_docs': []}
    
    async def scrape_document(
        self,
        page: Page,
        doc_url: str
    ) -> Optional[Dict]:
        """
        Scrape a single document page.
        
        Returns:
            Dict with title, content, metadata
        """
        try:
            await page.goto(doc_url, wait_until="networkidle", timeout=30000)
            
            # Wait for document content
            await asyncio.sleep(3)
            
            # Extract document data
            doc_data = await page.evaluate("""
                () => {
                    // Try to find title
                    const titleEl = document.querySelector('h1, .document-title, .title');
                    const title = titleEl ? titleEl.innerText : 'Untitled';
                    
                    // Get full text content
                    const contentEl = document.querySelector('.document-content, .content, main, article') || document.body;
                    const content = contentEl.innerText;
                    
                    // Try to extract document type
                    const typeEl = document.querySelector('.document-type, .type');
                    const docType = typeEl ? typeEl.innerText : '';
                    
                    // Get all metadata
                    const metadata = {};
                    const metaElements = document.querySelectorAll('[data-meta-key], .metadata-item');
                    metaElements.forEach(el => {
                        const key = el.getAttribute('data-meta-key') || el.className;
                        metadata[key] = el.innerText;
                    });
                    
                    return {
                        title,
                        content,
                        docType,
                        metadata,
                        contentLength: content.length
                    };
                }
            """)
            
            if doc_data['contentLength'] < 100:
                logger.warning(f"Document content too short: {doc_url}")
                return None
            
            return doc_data
        
        except Exception as e:
            logger.error(f"Error scraping document {doc_url}: {e}")
            return None
    
    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Split text into chunks."""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Try to break at sentence boundary
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
    
    async def process_and_store_document(
        self,
        doc_url: str,
        doc_data: Dict,
        db
    ) -> Optional[Document]:
        """Process and store document in database and vector store."""
        try:
            content = doc_data['content']
            title = doc_data['title']
            
            # Skip if too short
            if len(content) < 100:
                return None
            
            # Create hash
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            # Check if exists
            existing = db.query(Document).filter_by(source_url=doc_url).first()
            if existing:
                logger.info(f"Document already exists: {doc_url}")
                return existing
            
            # Detect language
            language = 'ka' if any('\u10A0' <= c <= '\u10FF' for c in content) else 'en'
            
            # Create document
            document = Document(
                title=title,
                document_type=doc_data.get('docType', 'unknown'),
                language=language,
                source_url=doc_url,
                full_text=content,
                file_hash=content_hash,
                metadata_json={
                    'source': 'infohub.rs.ge',
                    'scraped_at': datetime.utcnow().isoformat(),
                    'scraper': 'playwright',
                    **doc_data.get('metadata', {})
                },
                status='active',
            )
            db.add(document)
            db.flush()
            
            # Chunk and create embeddings
            chunks = self.chunk_text(content)
            logger.info(f"Created {len(chunks)} chunks for {title}")
            
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
                        'document_id': str(document.id),
                        'chunk_id': str(chunk.id),
                        'title': title,
                        'source_url': doc_url,
                        'document_type': doc_data.get('docType', 'unknown'),
                        'language': language,
                        'source': 'infohub.rs.ge',
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
            
            db.commit()
            self.documents_scraped += 1
            logger.info(f"✓ Stored: {title}")
            
            return document
        
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            db.rollback()
            return None
    
    async def scrape_with_search(
        self,
        search_query: str,
        max_documents: int = 10
    ) -> List[Document]:
        """
        Scrape documents using search query.
        
        Args:
            search_query: Georgian text to search for
            max_documents: Maximum documents to scrape
        
        Returns:
            List of Document objects
        """
        if not self.browser:
            await self.init_browser()
        
        db = SessionLocal()
        documents = []
        
        try:
            page = await self.browser.new_page()
            
            # Search URL
            search_url = f"https://infohub.rs.ge/ka/search?searchText={search_query}&skip=0&take=40"
            
            logger.info(f"Searching: {search_query}")
            search_results = await self.scrape_search_page(page, search_url)
            
            doc_links = search_results['unique_docs'][:max_documents]
            logger.info(f"Found {len(doc_links)} documents")
            
            # Scrape each document
            for doc_url in doc_links:
                doc_data = await self.scrape_document(page, doc_url)
                
                if doc_data:
                    document = await self.process_and_store_document(
                        doc_url,
                        doc_data,
                        db
                    )
                    
                    if document:
                        documents.append(document)
                
                await asyncio.sleep(1)  # Rate limiting
            
            await page.close()
        
        finally:
            db.close()
        
        return documents
    
    async def scrape_key_documents(self) -> Dict:
        """Scrape key tax documents."""
        key_searches = {
            'tax_code': 'საგადასახადო კოდექსი',
            'order_996': 'ბრძანება 996',
            'vat_guide': 'დღგ მეთოდოლოგია',
        }
        
        results = {}
        
        for key, query in key_searches.items():
            logger.info(f"Searching for {key}: {query}")
            docs = await self.scrape_with_search(query, max_documents=5)
            results[key] = {
                'query': query,
                'documents_found': len(docs),
                'documents': [{'title': d.title, 'url': d.source_url} for d in docs]
            }
        
        return results
