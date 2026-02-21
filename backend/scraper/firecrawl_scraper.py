"""
Firecrawl-based scraper for InfoHub SPA site.
"""
import asyncio
import logging
import hashlib
from typing import List, Dict, Optional
from datetime import datetime
import requests
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.document import Document, DocumentChunk
from rag.embeddings import embeddings_generator
from rag.vector_store import vector_store
from core.config import settings


logger = logging.getLogger(__name__)


class FirecrawlScraper:
    """Scraper using Firecrawl API for JavaScript-rendered sites."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.firecrawl.dev/v2"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.documents_scraped = 0
        self.pages_scraped = 0
    
    def scrape_url(self, url: str, formats: List[str] = None) -> Dict:
        """
        Scrape a single URL using Firecrawl.
        
        Args:
            url: URL to scrape
            formats: List of formats to return (markdown, html, links, etc.)
            
        Returns:
            Dictionary with scraped data
        """
        if formats is None:
            formats = ["markdown", "links"]
        
        try:
            response = requests.post(
                f"{self.base_url}/scrape",
                headers=self.headers,
                json={
                    "url": url,
                    "formats": formats
                },
                timeout=60
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
    
    def detect_language(self, text: str) -> str:
        """Detect language (Georgian, Russian, English)."""
        import re
        if re.search(r'[\u10A0-\u10FF]', text):
            return 'ka'
        if re.search(r'[\u0400-\u04FF]', text):
            return 'ru'
        return 'en'
    
    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """Split text into chunks."""
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
        markdown_content: str,
        metadata: Dict,
        db: Session
    ) -> Optional[Document]:
        """Process and store a document."""
        try:
            # Skip if too short
            if not markdown_content or len(markdown_content) < 100:
                logger.info(f"Skipping {url}: content too short")
                return None
            
            # Detect language
            language = self.detect_language(markdown_content)
            
            # Create document hash
            content_hash = hashlib.md5(markdown_content.encode()).hexdigest()
            
            # Check if exists
            existing = db.query(Document).filter_by(source_url=url).first()
            if existing:
                logger.info(f"Document already exists: {url}")
                return existing
            
            # Extract title from metadata or markdown
            title = metadata.get('title', 'Untitled')
            if not title or title == 'Untitled':
                # Try to get first heading from markdown
                lines = markdown_content.split('\n')
                for line in lines:
                    if line.startswith('#'):
                        title = line.lstrip('#').strip()
                        break
            
            # Create document metadata
            doc_metadata = {
                'source': 'infohub.rs.ge',
                'scraped_at': datetime.utcnow().isoformat(),
                'species': metadata.get('species'),
                'page': metadata.get('page'),
                'firecrawl': True,
            }
            
            document = Document(
                title=title,
                document_type='guideline',  # InfoHub documents are tax guidelines
                language=language,
                source_url=url,
                full_text=markdown_content,
                file_hash=content_hash,
                metadata_json=doc_metadata,
                status='active',
            )
            db.add(document)
            db.flush()
            
            # Chunk text
            chunks = self.chunk_text(markdown_content)
            logger.info(f"Created {len(chunks)} chunks for document {document.id}")
            
            # Generate embeddings
            if embeddings_generator.model:
                embeddings = embeddings_generator.encode(chunks)
                
                # Store chunks
                vector_ids = []
                vector_embeddings = []
                vector_metadatas = []
                vector_documents = []
                
                for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                    chunk = DocumentChunk(
                        document_id=document.id,
                        chunk_index=i,
                        content=chunk_text,
                        metadata_={'position': i, 'total_chunks': len(chunks)},
                    )
                    db.add(chunk)
                    db.flush()
                    
                    vector_ids.append(f"doc_{document.id}_chunk_{chunk.id}")
                    vector_embeddings.append(embedding)
                    vector_metadatas.append({
                        'document_id': str(document.id),
                        'chunk_id': str(chunk.id),
                        'title': title,
                        'url': url,
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
                    logger.info(f"Added {len(vector_ids)} chunks to vector store")
            
            db.commit()
            self.documents_scraped += 1
            logger.info(f"Successfully processed: {url}")
            
            return document
            
        except Exception as e:
            logger.error(f"Error processing document {url}: {e}")
            db.rollback()
            return None
    
    async def scrape_paginated_section(
        self,
        base_url: str,
        species: str,
        max_pages: int,
        page_size: int = 40,
        db: Session = None
    ) -> List[Document]:
        """
        Scrape a paginated section of InfoHub.
        
        Args:
            base_url: Base URL (e.g., https://infohub.rs.ge/ka)
            species: Section type (NewDocument, LegislativeNews, Bill)
            max_pages: Maximum pages to scrape
            page_size: Items per page
            db: Database session
            
        Returns:
            List of processed documents
        """
        documents = []
        
        for page in range(1, max_pages + 1):
            url = f"{base_url}?species={species}&page={page}&pageSize={page_size}"
            
            logger.info(f"Scraping page {page}/{max_pages}: {url}")
            
            # Scrape page with Firecrawl
            result = self.scrape_url(url, formats=["markdown", "links"])
            
            if not result or 'data' not in result:
                logger.warning(f"Failed to scrape {url}")
                continue
            
            data = result['data']
            markdown = data.get('markdown', '')
            links = data.get('links', [])
            metadata = data.get('metadata', {})
            
            # Process the page listing
            self.pages_scraped += 1
            
            # Extract document links from the page
            # InfoHub likely has links to individual documents
            doc_links = [
                link for link in links
                if 'infohub.rs.ge' in link and 'document' in link.lower()
            ]
            
            logger.info(f"Found {len(doc_links)} document links on page {page}")
            
            # Scrape individual documents
            for doc_url in doc_links[:10]:  # Limit per page to avoid rate limits
                try:
                    doc_result = self.scrape_url(doc_url)
                    if doc_result and 'data' in doc_result:
                        doc_data = doc_result['data']
                        doc_markdown = doc_data.get('markdown', '')
                        doc_metadata = doc_data.get('metadata', {})
                        doc_metadata['species'] = species
                        doc_metadata['page'] = page
                        
                        document = await self.process_document(
                            doc_url,
                            doc_markdown,
                            doc_metadata,
                            db
                        )
                        
                        if document:
                            documents.append(document)
                        
                        # Rate limiting
                        await asyncio.sleep(1)
                
                except Exception as e:
                    logger.error(f"Error processing document {doc_url}: {e}")
                    continue
            
            # Rate limiting between pages
            await asyncio.sleep(2)
        
        return documents
    
    async def scrape_all_sections(
        self,
        base_url: str = "https://infohub.rs.ge/ka",
        max_pages_per_section: int = 10
    ) -> Dict:
        """
        Scrape all sections of InfoHub.
        
        Args:
            base_url: Base URL
            max_pages_per_section: Max pages per section
            
        Returns:
            Summary dictionary
        """
        sections = [
            {"species": "NewDocument", "name": "ახალი დოკუმენტები", "total_pages": 258},
            {"species": "LegislativeNews", "name": "საკანონმდებლო სიახლეები", "total_pages": 87},
            {"species": "Bill", "name": "კანონპროექტები", "total_pages": 2},
        ]
        
        db = SessionLocal()
        all_documents = []
        
        try:
            for section in sections:
                species = section['species']
                total_pages = section['total_pages']
                pages_to_scrape = min(max_pages_per_section, total_pages)
                
                logger.info(f"Scraping section: {section['name']} ({pages_to_scrape}/{total_pages} pages)")
                
                documents = await self.scrape_paginated_section(
                    base_url=base_url,
                    species=species,
                    max_pages=pages_to_scrape,
                    db=db
                )
                
                all_documents.extend(documents)
                logger.info(f"Section {section['name']}: {len(documents)} documents")
        
        finally:
            db.close()
        
        return {
            'documents_scraped': self.documents_scraped,
            'pages_scraped': self.pages_scraped,
            'documents': [{'id': doc.id, 'title': doc.title, 'url': doc.url} for doc in all_documents],
        }
