#!/usr/bin/env python
"""One-off import: Supreme Court administrative-practice digests (2013-2017).

supremecourt.ge publishes 97 monthly PDF digests of administrative-chamber
decisions (tax/customs disputes are administrative cases) — the only bulk
court practice publicly available in Georgia (see П4 recon in
docs/CONCEPT_COMPLIANCE_AUDIT_2026-07.md). PDFs use the legacy AcadNusx
glyph encoding (Georgian rendered as Latin bytes); text is converted to
Unicode Georgian before chunking/embedding.

Digests are compilations, not single decisions: rows get
metadata.kind='digest' and are excluded from decision_facts extraction.

Usage (inside infohub-backend; requires pypdf):
    python scripts/import_supreme_court_digests.py --limit 2   # probe
    python scripts/import_supreme_court_digests.py             # all
"""
import argparse
import hashlib
import io
import logging
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import SessionLocal
from models.document import Document, DocumentChunk
from rag.embeddings import embeddings_generator
from rag.vector_store_pgvector import vector_store
from scraper.infohub_api_scraper import InfoHubAPIScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("sc_digests")

BASE = "https://www.supremecourt.ge"
LISTING_URL = f"{BASE}/decisions/administratsiuli-samartlis-saqmeebze"
FILENAME_RE = re.compile(r"/pdf/(\d{4})w-administr-krebuli(\d+)\.pdf$")

# AcadNusx legacy font: Latin glyph -> Unicode Georgian letter.
ACADNUSX = str.maketrans({
    "a": "ა", "b": "ბ", "g": "გ", "d": "დ", "e": "ე", "v": "ვ", "z": "ზ",
    "T": "თ", "i": "ი", "k": "კ", "l": "ლ", "m": "მ", "n": "ნ", "o": "ო",
    "p": "პ", "J": "ჟ", "r": "რ", "s": "ს", "t": "ტ", "u": "უ", "f": "ფ",
    "q": "ქ", "R": "ღ", "y": "ყ", "S": "შ", "C": "ჩ", "c": "ც", "Z": "ძ",
    "w": "წ", "W": "ჭ", "x": "ხ", "j": "ჯ", "h": "ჰ",
})


def acadnusx_to_unicode(text: str) -> str:
    lines = []
    for line in text.splitlines():
        # URLs and case numbers stay Latin; everything else is Georgian glyphs.
        if "http" in line or "www." in line:
            lines.append(line)
        else:
            lines.append(line.translate(ACADNUSX))
    return "\n".join(lines)


def fetch(url: str, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (InfoHubAI import)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def pdf_urls() -> list:
    html = fetch(LISTING_URL)
    urls = sorted(set(re.findall(r'href="(/files/upload-file/pdf/\d{4}w-administr-krebuli\d+\.pdf)"', html)))
    return [BASE + u for u in urls]


def extract_pdf_text(blob: bytes) -> tuple:
    try:
        from pypdf import PdfReader
    except ImportError:  # image pins the predecessor PyPDF2 3.x (same API)
        from PyPDF2 import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages), len(reader.pages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="max digests to import (0 = all)")
    args = parser.parse_args()

    scraper = InfoHubAPIScraper()  # reused for chunk_text only
    urls = pdf_urls()
    logger.info(f"Digest PDFs on listing page: {len(urls)}")
    if args.limit:
        urls = urls[: args.limit]

    done = skipped = failed = 0
    for url in urls:
        db = SessionLocal()
        try:
            if db.query(Document.id).filter_by(source_url=url).first():
                skipped += 1
                continue
            m = FILENAME_RE.search(url)
            year, issue = (int(m.group(1)), int(m.group(2))) if m else (None, None)
            blob = fetch(url, binary=True)
            raw_text, n_pages = extract_pdf_text(blob)
            text = acadnusx_to_unicode(raw_text)
            if len(text) < 5000:
                logger.warning(f"Skipping {url}: extracted only {len(text)} chars")
                failed += 1
                continue

            title = "საქართველოს უზენაესი სასამართლოს გადაწყვეტილებანი ადმინისტრაციულ საქმეებზე"
            if year and issue:
                title += f" — {year}, №{issue}"
            document = Document(
                source_url=url,
                title=title,
                document_type="court_decision",
                document_number=f"{year}-{issue}" if year and issue else None,
                date_published=date(year, issue, 1) if year and 1 <= (issue or 0) <= 12 else (date(year, 1, 1) if year else None),
                authority="საქართველოს უზენაესი სასამართლო",
                language="ka",
                full_text=text,
                metadata_json={"kind": "digest", "source": "supremecourt.ge", "pages": n_pages},
                file_hash=hashlib.md5(text.encode("utf-8")).hexdigest(),
            )
            db.add(document)
            db.flush()

            chunks = scraper.chunk_text(text)
            embeddings = embeddings_generator.encode(chunks) if embeddings_generator.model else None
            for i, chunk_text in enumerate(chunks):
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=i,
                    content=chunk_text,
                    metadata_json={"position": i, "total_chunks": len(chunks), "kind": "digest"},
                )
                if embeddings is not None:
                    emb = embeddings[i]
                    chunk_vals = emb.tolist() if hasattr(emb, "tolist") else list(emb)
                    setattr(chunk, vector_store.embedding_column, chunk_vals)
                db.add(chunk)
            db.commit()
            done += 1
            logger.info(f"Imported {url} ({n_pages}p, {len(chunks)} chunks) [{done} done]")
            time.sleep(1)
        except Exception as e:
            db.rollback()
            failed += 1
            logger.error(f"Failed {url}: {e}")
        finally:
            db.close()

    logger.info(f"Finished. imported={done} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
