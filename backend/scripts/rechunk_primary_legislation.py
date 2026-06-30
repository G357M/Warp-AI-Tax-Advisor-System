"""Re-chunk primary legislation (law/regulation/guideline) by article and re-embed.

Each chunk becomes one whole article ("მუხლი N") so it embeds coherently with a
topical query and carries article_ref for precise citation. Court decisions are
NOT touched. Per-document transactions make the run resumable and partial-safe.

Run this AFTER reembed_bge_m3.py has fully populated embedding_v2 for the corpus,
with INFOHUB_EMBEDDING_V2=1 set — DocumentChunk.embedding is a fixed Vector(768)
column (the old paraphrase-mpnet dimension), so a bge-m3 1024-d vector cannot be
written there; it goes into embedding_v2 via raw SQL instead, mirroring
reembed_bge_m3.py. Without the env var this falls back to populating the old
768-d `.embedding` column, which is correct if you ever need to re-chunk before
the bge-m3 migration, but then embedding_v2 stays NULL for the new chunks until
reembed_bge_m3.py is re-run (it is resumable and will pick them up).

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
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
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

    # Assign ids up front (rather than relying on the ORM's flush-time default) so
    # they're available below for the embedding_v2 raw-SQL UPDATE.
    objs = []
    for idx, ch in enumerate(new_chunks_data):
        objs.append(
            DocumentChunk(
                id=uuid4(),
                document_id=doc.id,
                chunk_index=idx,
                content=ch["content"],
                tokens_count=ch.get("tokens_count"),
                metadata_json=ch.get("metadata") or {},
            )
        )

    # Embed in batches. bge-m3 (1024-d) cannot go into the fixed Vector(768)
    # `.embedding` column — it's written to embedding_v2 via raw SQL instead.
    use_v2 = embeddings_generator.use_v2
    contents = [o.content for o in objs]
    v2_vectors = {}
    for i in range(0, len(contents), EMBED_BATCH):
        vectors = embeddings_generator.encode(contents[i : i + EMBED_BATCH])
        batch = objs[i : i + EMBED_BATCH]
        if use_v2:
            for obj, vec in zip(batch, vectors):
                v2_vectors[obj.id] = vec
        else:
            for obj, vec in zip(batch, vectors):
                obj.embedding = vec

    db.add_all(objs)
    if use_v2:
        db.flush()  # rows must exist before the UPDATE below can match their ids
        for obj_id, vec in v2_vectors.items():
            vec_str = "[" + ",".join(str(float(x)) for x in vec) + "]"
            db.execute(
                text("UPDATE document_chunks SET embedding_v2 = CAST(:v AS vector) WHERE id = :id"),
                {"v": vec_str, "id": obj_id},
            )
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
        if embeddings_generator.use_v2:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS document_chunks_embedding_v2_idx
                ON document_chunks USING hnsw (embedding_v2 vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """))
            db.commit()
            total_vectors = db.execute(
                text("SELECT count(*) FROM document_chunks WHERE embedding_v2 IS NOT NULL")
            ).scalar()
        else:
            vector_store.create_index()
            total_vectors = vector_store.get_count()
        logger.info(f"DONE. Re-chunked {done} docs into {new_total} article chunks. "
                    f"Total vectors: {total_vectors}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
