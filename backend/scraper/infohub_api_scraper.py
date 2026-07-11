"""
Direct-API scraper for infohub.rs.ge.

infohub.rs.ge is a client-rendered Angular SPA — its HTML contains no content
or links, so HTML crawling yields nothing. The SPA reads from a public JSON API
at https://infohubapi.rs.ge/api (header ``languagecode: ka|ru|en``). This
scraper talks to that API directly, in two steps:

  1. LIST   GET /documents?skip=<n>&take=<n>&species=<S>
            -> {"meta": {"total": N}, "data": [ {uniqueKey, name, type, ...}, ... ]}
  2. DETAIL GET /documents/<uniqueKey>/details-by-key?openFromSearch=false
            -> { ..., "description": "<full HTML body>", ... }

The list's ``additionalDescription`` is only a short summary; the full document
text lives in the detail's ``description``. Documents are grouped by ``species``:
NewDocument, LegislativeNews, Bill. No authentication is required.

The corpus is already backfilled, so the nightly job is incremental: it walks
the newest documents per species and stops a species once a page yields no new
documents (everything already in the DB).

Storage reuses the Document/DocumentChunk + embeddings pipeline; embeddings are
written directly onto the chunk rows (searched by pgvector).
"""
import hashlib
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from core.config import settings
from core.database import SessionLocal
from models.document import Document, DocumentChunk
from processor.chunker import text_chunker
from rag.embeddings import embeddings_generator
from rag.vector_store_pgvector import vector_store
from scraper.normalize import classify_news_subtype, infer_document_type, parse_receipt_date

logger = logging.getLogger(__name__)

API_BASE = "https://infohubapi.rs.ge/api"
SPECIES = ["NewDocument", "LegislativeNews", "Bill"]


class InfoHubAPIScraper:
    """Scrape documents from the infohub.rs.ge public JSON API."""

    def __init__(self, language: str = "ka", page_size: int = 50, delay: Optional[float] = None):
        self.language = language
        self.page_size = page_size
        self.delay = settings.SCRAPER_DELAY if delay is None else delay
        self.documents_scraped = 0
        self.pages_visited = 0

    # ---- HTTP ---------------------------------------------------------------
    def _get(self, url: str) -> Optional[dict]:
        req = urllib.request.Request(url, headers={
            "User-Agent": "InfoHubAI-Bot/1.0",
            "Accept": "application/json, text/plain, */*",
            "languagecode": self.language,
            "Referer": "https://infohub.rs.ge/",
            "Origin": "https://infohub.rs.ge",
        })
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            logger.error(f"API HTTP {e.code} for {url}")
        except Exception as e:
            logger.error(f"API error for {url}: {e}")
        return None

    def fetch_page(self, species: str, skip: int) -> tuple:
        """Return (list_items, total) for one page of a species."""
        url = f"{API_BASE}/documents?skip={skip}&take={self.page_size}&species={species}"
        payload = self._get(url)
        if not payload:
            return [], 0
        self.pages_visited += 1
        return payload.get("data", []), (payload.get("meta") or {}).get("total", 0)

    def fetch_details(self, unique_key: str) -> Optional[dict]:
        """Return the full document detail (incl. ``description``) for a uniqueKey."""
        url = f"{API_BASE}/documents/{unique_key}/details-by-key?openFromSearch=false"
        return self._get(url)

    # ---- parsing ------------------------------------------------------------
    @staticmethod
    def _html_to_text(html: str) -> str:
        if not html:
            return ""
        return BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()

    def build_text(self, detail: dict) -> str:
        """Build the full document text from a detail object."""
        parts = []
        name = (detail.get("name") or "").strip()
        if name:
            parts.append(name)
        for key in ("type", "baseType"):
            t = detail.get(key)
            if isinstance(t, dict) and t.get("name"):
                parts.append(t["name"])
        # full body lives in 'description'; fall back to the summary
        body = self._html_to_text(detail.get("description") or detail.get("additionalDescription") or "")
        if body:
            parts.append(body)
        return "\n\n".join(parts).strip()

    def chunk_text(self, text: str) -> List[str]:
        size, overlap = settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP
        if len(text) <= size:
            return [text]
        chunks, start = [], 0
        while start < len(text):
            chunk = text[start:start + size].strip()
            if chunk:
                chunks.append(chunk)
            start += size - overlap
        return chunks

    # ---- storage ------------------------------------------------------------
    def store(self, detail: dict, source_url: str, db: Session) -> Optional[Document]:
        text = self.build_text(detail)
        if not text or len(text) < 100:
            logger.info(f"Skipping {source_url}: content too short")
            return None

        doc_type = detail.get("type")
        doc_type_name = doc_type.get("name") if isinstance(doc_type, dict) else None
        base_type = detail.get("baseType")
        base_type_name = base_type.get("name") if isinstance(base_type, dict) else None
        title = detail.get("name") or "Untitled"
        type_meta = {
            "type": doc_type_name,
            "baseType": base_type_name,
            "species": detail.get("species"),
        }
        subtype = classify_news_subtype(title, type_meta)
        document = Document(
            source_url=source_url,
            title=title,
            document_type=infer_document_type(title, type_meta),
            subtype=subtype,
            subtype_source="rule" if subtype else None,
            date_published=parse_receipt_date(detail.get("receiptDate")),
            document_number=(str(detail.get("documentNumber")).strip() or None) if detail.get("documentNumber") else None,
            full_text=text,
            language=self.language,
            metadata_json={
                "species": detail.get("species"),
                "documentNumber": detail.get("documentNumber"),
                "uniqueKey": detail.get("uniqueKey"),
                "receiptDate": detail.get("receiptDate"),
                "type": doc_type_name,
            },
            file_hash=hashlib.md5(text.encode("utf-8")).hexdigest(),
        )
        db.add(document)
        db.flush()

        # Primary legislation is chunked one-article-per-chunk so each chunk
        # carries article_ref for exact citation resolution (П1); everything
        # else keeps the plain fixed-size chunking.
        if document.document_type in ("law", "regulation", "guideline"):
            chunk_dicts = text_chunker.chunk_by_article(text, {})
            chunk_contents = [c["content"] for c in chunk_dicts]
            chunk_metas = [
                {**(c.get("metadata") or {}), "position": i, "total_chunks": len(chunk_dicts)}
                for i, c in enumerate(chunk_dicts)
            ]
        else:
            chunk_contents = self.chunk_text(text)
            chunk_metas = [
                {"position": i, "total_chunks": len(chunk_contents)}
                for i in range(len(chunk_contents))
            ]
        embeddings = embeddings_generator.encode(chunk_contents) if embeddings_generator.model else None
        for i, content in enumerate(chunk_contents):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=i,
                content=content,
                metadata_json=chunk_metas[i],
            )
            if embeddings is not None:
                emb = embeddings[i]
                emb_list = emb.tolist() if hasattr(emb, "tolist") else list(emb)
                setattr(chunk, vector_store.embedding_column, emb_list)
            db.add(chunk)

        db.commit()
        self.documents_scraped += 1
        return document

    # ---- driver -------------------------------------------------------------
    def scrape(self, species_list: Optional[List[str]] = None, max_docs: int = 200) -> Dict:
        """Walk newest documents per species; ingest new ones up to max_docs.

        Stops a species early once a full page contains no new documents
        (incremental catch-up).
        """
        species_list = species_list or SPECIES
        for species in species_list:
            skip = 0
            while self.documents_scraped < max_docs:
                items, total = self.fetch_page(species, skip)
                if not items:
                    break
                new_on_page = 0
                for item in items:
                    if self.documents_scraped >= max_docs:
                        break
                    uid = item.get("uniqueKey")
                    if not uid:
                        continue
                    source_url = f"https://infohub.rs.ge/{self.language}/workspace/document/{uid}"
                    db = SessionLocal()
                    try:
                        if db.query(Document.id).filter_by(source_url=source_url).first():
                            continue  # already ingested — skip (no detail fetch)
                        detail = self.fetch_details(uid)
                        if not detail:
                            continue
                        self.store(detail, source_url, db)
                        new_on_page += 1
                        if self.delay:
                            time.sleep(self.delay)
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Error processing {uid}: {e}")
                    finally:
                        db.close()
                logger.info(f"[{species}] skip={skip}/{total} | new this page: {new_on_page} | total new: {self.documents_scraped}")
                if new_on_page == 0:
                    logger.info(f"[{species}] no new documents on page — caught up.")
                    break
                skip += self.page_size
                if skip >= total:
                    break
            if self.documents_scraped >= max_docs:
                break
        return {"documents_scraped": self.documents_scraped, "pages_visited": self.pages_visited}
