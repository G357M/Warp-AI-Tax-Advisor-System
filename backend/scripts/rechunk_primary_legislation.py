"""Re-chunk primary legislation (law/regulation/guideline) by article and re-embed.

Each chunk becomes one whole article ("მუხლი N") so it embeds coherently with a
topical query and carries article_ref for precise citation. Court decisions are
NOT touched. Per-document transactions make the run resumable and partial-safe.

Usage (run inside the infohub-backend container):
    python /app/scripts/rechunk_primary_legislation.py                 # all primary legislation
    python /app/scripts/rechunk_primary_legislation.py --source-url URL # single document
    python /app/scripts/rechunk_primary_legislation.py --doc-type law   # one type
    python /app/scripts/rechunk_primary_legislation.py --limit 1        # first N docs (test)
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.database import SessionLocal
from models.document import Document, DocumentChunk
from processor.chunker import text_chunker
from rag.embeddings import embeddings_generator
from rag.vector_store_pgvector import vector_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rechunk")

STATE_FILE = "/tmp/rechunk_processed.txt"
EMBED_BATCH = 50


def _load_processed() -> set:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as fh:
            return {line.strip() for line in fh if line.strip()}
    return set()


def _mark_processed(doc_id: str) -> None:
    with open(STATE_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"{doc_id}\n")


def rechunk_document(db, doc: Document) -> int:
    """Re-chunk one document by article and re-embed. Returns new chunk count."""
    full_text = doc.full_text or ""
    if not full_text.strip():
        logger.warning(f"  skip {doc.id} — empty full_text (keeping existing chunks)")
        return -1

    base_meta = {
        "document_id": str(doc.id),
        "title": doc.title,
        "document_type": doc.document_type,
        "source_url": doc.source_url,
    }
    new_chunks_data = text_chunker.chunk_by_article(full_text, base_meta)
    if not new_chunks_data:
        logger.warning(f"  skip {doc.id} — chunker produced nothing")
        return -1

    # Replace old chunks atomically with the new article-level ones.
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()

    objs = []
    for idx, ch in enumerate(new_chunks_data):
        objs.append(
            DocumentChunk(
                document_id=doc.id,
                chunk_index=idx,
                content=ch["content"],
                tokens_count=ch.get("tokens_count"),
                metadata_json=ch.get("metadata") or {},
            )
        )

    # Embed in batches and attach vectors before insert.
    contents = [o.content for o in objs]
    for i in range(0, len(contents), EMBED_BATCH):
        vectors = embeddings_generator.encode(contents[i : i + EMBED_BATCH])
        for obj, vec in zip(objs[i : i + EMBED_BATCH], vectors):
            obj.embedding = vec

    db.add_all(objs)
    db.commit()
    return len(objs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--doc-type", default=None, choices=["law", "regulation", "guideline"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = db.query(Document)
        if args.source_url:
            q = q.filter(Document.source_url == args.source_url)
        else:
            types = [args.doc_type] if args.doc_type else ["law", "regulation", "guideline"]
            q = q.filter(Document.document_type.in_(types))
        # law first (smallest + most important), then guideline, then regulation
        q = q.order_by(Document.document_type.asc(), Document.created_at.asc())
        docs = q.all()
        if args.limit:
            docs = docs[: args.limit]

        processed = _load_processed()
        total = len(docs)
        logger.info(f"Target docs: {total} | already processed: {len(processed)}")

        done = 0
        new_total = 0
        for n, doc in enumerate(docs, 1):
            if str(doc.id) in processed:
                continue
            try:
                count = rechunk_document(db, doc)
                if count >= 0:
                    new_total += count
                    done += 1
                _mark_processed(str(doc.id))
            except Exception as exc:
                db.rollback()
                logger.error(f"  FAILED {doc.id} ({doc.title[:40]}): {exc}")
            if n % 25 == 0 or n == total:
                logger.info(f"[{n}/{total}] processed={done} new_chunks={new_total}")

        logger.info("Ensuring HNSW index exists...")
        vector_store.create_index()
        logger.info(f"DONE. Re-chunked {done} docs into {new_total} article chunks. "
                    f"Total vectors: {vector_store.get_count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
