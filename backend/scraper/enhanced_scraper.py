"""
Enhanced InfoHub scraper with document type priorities.
Scrapes legislative documents, orders, guidelines, and case law.
"""
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime

from scraper.firecrawl_scraper import FirecrawlScraper
from core.database import SessionLocal
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


# Document type mappings from Georgian to English
DOCUMENT_TYPE_MAP = {
    # Legislative acts (Priority 1 - Most important)
    'საქართველოს კონსტიტუცია/კონსტიტუციური კანონი': 'constitution',
    'საქართველოს ორგანული კანონი': 'organic_law',
    'საქართველოს კანონი': 'law',  # Tax Code is here
    'მთავრობის დადგენილება': 'government_resolution',
    'ბრძანება': 'order',  # Order 996 is here
    'ერთობლივი ბრძანება': 'joint_order',
    
    # Guidelines and instructions (Priority 2)
    'სიტუაციური სახელმძღვანელო': 'situational_guideline',
    'მეთოდური მითითება': 'methodological_guideline',
    'პროცედურული სახელმძღვანელო': 'procedural_guideline',
    'ბრძანება ინსტრუქციების დამტკიცების შესახებ': 'instruction_order',
    'სტანდარტი': 'standard',
    
    # Case law and decisions (Priority 3)
    'შემოსავლების სამსახურის დავების გადაწყვეტილება': 'revenue_service_decision',
    'ფინანსთა სამინისტროს დავების გადაწყვეტილება': 'ministry_decision',
    'უზენაესი სასამართლოს გადაწყვეტილება': 'supreme_court_decision',
    'სააპელაციო სასამართლოს გადაწყვეტილება': 'appeals_court_decision',
    'საქალაქო სასამართლოს გადაწყვეტილება': 'city_court_decision',
    'საჯარო გადაწყვეტილება': 'public_decision',
    
    # International agreements (Priority 2)
    'სახელმწიფოთაშორისი ხელშეკრულება/შეთანხმება': 'international_agreement',
    'მთავრობათაშორისი ხელშეკრულება/შეთანხმება': 'intergovernmental_agreement',
}


# Priority weights for document types (higher = more important)
DOCUMENT_PRIORITY = {
    'law': 100,  # Tax Code
    'order': 90,  # Order 996 and similar
    'government_resolution': 85,
    'organic_law': 95,
    'constitution': 100,
    'methodological_guideline': 70,
    'situational_guideline': 60,
    'instruction_order': 65,
    'international_agreement': 75,
    'ministry_decision': 40,
    'revenue_service_decision': 35,
    'supreme_court_decision': 50,
    'appeals_court_decision': 45,
    'city_court_decision': 40,
    'public_decision': 35,
}


# Search queries for key documents
KEY_DOCUMENT_SEARCHES = {
    'tax_code': {
        'query': 'საგადასახადო კოდექსი',
        'type': 'law',
        'priority': 100,
    },
    'order_996': {
        'query': 'ბრძანება 996',
        'type': 'order',
        'priority': 90,
    },
    'vat_methodology': {
        'query': 'დღგ მეთოდოლოგია',
        'type': 'methodological_guideline',
        'priority': 80,
    },
    'income_tax_law': {
        'query': 'საშემოსავლო გადასახადი კანონი',
        'type': 'law',
        'priority': 95,
    },
}


class EnhancedInfoHubScraper:
    """Enhanced scraper with document type awareness and prioritization."""
    
    def __init__(self, api_key: str):
        self.firecrawl = FirecrawlScraper(api_key)
        self.stats = {
            'by_type': {},
            'by_priority': {'high': 0, 'medium': 0, 'low': 0},
            'total': 0,
        }
    
    def get_document_priority(self, doc_type: str) -> int:
        """Get priority weight for document type."""
        return DOCUMENT_PRIORITY.get(doc_type, 30)
    
    def classify_priority(self, priority_weight: int) -> str:
        """Classify priority as high/medium/low."""
        if priority_weight >= 80:
            return 'high'
        elif priority_weight >= 50:
            return 'medium'
        return 'low'
    
    async def search_key_documents(self, db: Session) -> List[Dict]:
        """
        Search and scrape key foundational documents.
        
        Returns:
            List of scraped document URLs
        """
        logger.info("Searching for key foundational documents...")
        found_documents = []
        
        for doc_key, doc_info in KEY_DOCUMENT_SEARCHES.items():
            logger.info(f"Searching for {doc_key}: {doc_info['query']}")
            
            # Use Firecrawl to search InfoHub
            search_url = f"https://infohub.rs.ge/ka?search={doc_info['query']}"
            
            try:
                result = self.firecrawl.scrape_url(search_url, formats=["markdown", "links"])
                
                if result and 'data' in result:
                    data = result['data']
                    links = data.get('links', [])
                    
                    # Filter document links
                    doc_links = [
                        link for link in links
                        if 'infohub.rs.ge' in link and '/document/' in link
                    ]
                    
                    logger.info(f"Found {len(doc_links)} links for {doc_key}")
                    
                    # Scrape first relevant document
                    for doc_url in doc_links[:3]:  # Check first 3 results
                        doc_result = self.firecrawl.scrape_url(doc_url)
                        
                        if doc_result and 'data' in doc_result:
                            doc_data = doc_result['data']
                            markdown = doc_data.get('markdown', '')
                            
                            # Process document
                            metadata = {
                                'key_document': doc_key,
                                'search_query': doc_info['query'],
                                'priority': doc_info['priority'],
                                'document_type': doc_info['type'],
                            }
                            
                            document = await self.firecrawl.process_document(
                                doc_url,
                                markdown,
                                metadata,
                                db
                            )
                            
                            if document:
                                found_documents.append({
                                    'key': doc_key,
                                    'url': doc_url,
                                    'title': document.title,
                                    'type': doc_info['type'],
                                })
                                logger.info(f"✓ Scraped {doc_key}: {document.title}")
                                break
                        
                        await asyncio.sleep(2)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error searching for {doc_key}: {e}")
                continue
            
            await asyncio.sleep(3)  # Rate limiting between searches
        
        return found_documents
    
    async def scrape_by_document_type(
        self,
        base_url: str,
        document_type_filter: str,
        max_documents: int = 50,
        db: Session = None
    ) -> List[Dict]:
        """
        Scrape documents filtered by document type.
        
        Args:
            base_url: InfoHub base URL
            document_type_filter: Georgian document type name
            max_documents: Maximum documents to scrape
            db: Database session
        
        Returns:
            List of scraped documents
        """
        doc_type_en = DOCUMENT_TYPE_MAP.get(document_type_filter, 'unknown')
        priority = self.get_document_priority(doc_type_en)
        priority_class = self.classify_priority(priority)
        
        logger.info(f"Scraping {document_type_filter} (priority: {priority_class}/{priority})")
        
        # Build search URL with document type filter
        search_url = f"{base_url}?documentType={document_type_filter}"
        
        scraped_docs = []
        page = 1
        docs_count = 0
        
        while docs_count < max_documents:
            paginated_url = f"{search_url}&page={page}"
            
            try:
                result = self.firecrawl.scrape_url(paginated_url, formats=["markdown", "links"])
                
                if not result or 'data' not in result:
                    break
                
                data = result['data']
                links = data.get('links', [])
                
                # Extract document links
                doc_links = [
                    link for link in links
                    if 'infohub.rs.ge' in link and '/document/' in link
                ]
                
                if not doc_links:
                    break
                
                logger.info(f"Page {page}: found {len(doc_links)} documents")
                
                # Scrape individual documents
                for doc_url in doc_links:
                    if docs_count >= max_documents:
                        break
                    
                    try:
                        doc_result = self.firecrawl.scrape_url(doc_url)
                        
                        if doc_result and 'data' in doc_result:
                            doc_data = doc_result['data']
                            markdown = doc_data.get('markdown', '')
                            
                            metadata = {
                                'document_type_ka': document_type_filter,
                                'document_type': doc_type_en,
                                'priority': priority,
                                'priority_class': priority_class,
                            }
                            
                            document = await self.firecrawl.process_document(
                                doc_url,
                                markdown,
                                metadata,
                                db
                            )
                            
                            if document:
                                scraped_docs.append({
                                    'url': doc_url,
                                    'title': document.title,
                                    'type': doc_type_en,
                                    'priority': priority,
                                })
                                docs_count += 1
                                
                                # Update stats
                                self.stats['by_type'][doc_type_en] = self.stats['by_type'].get(doc_type_en, 0) + 1
                                self.stats['by_priority'][priority_class] += 1
                                self.stats['total'] += 1
                        
                        await asyncio.sleep(1)  # Rate limiting
                    
                    except Exception as e:
                        logger.error(f"Error scraping document {doc_url}: {e}")
                        continue
                
                page += 1
                await asyncio.sleep(2)  # Rate limiting between pages
            
            except Exception as e:
                logger.error(f"Error scraping page {page}: {e}")
                break
        
        return scraped_docs
    
    async def scrape_priority_documents(
        self,
        base_url: str = "https://infohub.rs.ge/ka",
        high_priority_limit: int = 100,
        medium_priority_limit: int = 50,
        low_priority_limit: int = 20
    ) -> Dict:
        """
        Scrape documents by priority: high priority first.
        
        Returns:
            Summary statistics
        """
        db = SessionLocal()
        
        try:
            # Step 1: Search for key foundational documents
            logger.info("=== STEP 1: Searching key documents ===")
            key_docs = await self.search_key_documents(db)
            logger.info(f"Found {len(key_docs)} key documents")
            
            # Step 2: Scrape high-priority document types
            logger.info("=== STEP 2: Scraping high-priority documents ===")
            high_priority_types = [
                'საქართველოს კანონი',  # Laws (Tax Code)
                'ბრძანება',  # Orders (Order 996)
                'მთავრობის დადგენილება',  # Government resolutions
            ]
            
            for doc_type in high_priority_types:
                await self.scrape_by_document_type(
                    base_url,
                    doc_type,
                    max_documents=high_priority_limit,
                    db=db
                )
            
            # Step 3: Scrape medium-priority document types
            logger.info("=== STEP 3: Scraping medium-priority documents ===")
            medium_priority_types = [
                'მეთოდური მითითება',  # Methodological guidelines
                'სიტუაციური სახელმძღვანელო',  # Situational guidelines
                'ბრძანება ინსტრუქციების დამტკიცების შესახებ',  # Instruction orders
            ]
            
            for doc_type in medium_priority_types:
                await self.scrape_by_document_type(
                    base_url,
                    doc_type,
                    max_documents=medium_priority_limit,
                    db=db
                )
            
            # Step 4: Scrape low-priority document types (case law)
            logger.info("=== STEP 4: Scraping low-priority documents ===")
            low_priority_types = [
                'უზენაესი სასამართლოს გადაწყვეტილება',  # Supreme court
                'ფინანსთა სამინისტროს დავების გადაწყვეტილება',  # Ministry decisions
            ]
            
            for doc_type in low_priority_types:
                await self.scrape_by_document_type(
                    base_url,
                    doc_type,
                    max_documents=low_priority_limit,
                    db=db
                )
            
            logger.info("=== SCRAPING COMPLETE ===")
            logger.info(f"Total documents: {self.stats['total']}")
            logger.info(f"High priority: {self.stats['by_priority']['high']}")
            logger.info(f"Medium priority: {self.stats['by_priority']['medium']}")
            logger.info(f"Low priority: {self.stats['by_priority']['low']}")
            logger.info(f"By type: {self.stats['by_type']}")
            
            return {
                'key_documents': key_docs,
                'statistics': self.stats,
            }
        
        finally:
            db.close()
