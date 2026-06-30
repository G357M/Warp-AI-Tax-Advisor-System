"""Re-embed the whole corpus with BAAI/bge-m3 into document_chunks.embedding_v2 (1024-d).

bge-m3 actually discriminates Georgian law and works cross-lingually (ru/en query vs
ka corpus) without translation, unlike the old paraphrase-mpnet (768-d, near-random on
Georgian). The new vectors go into a SEPARATE column so the old `embedding` stays as an
instant rollback; serving switches to embedding_v2 only after validation.

Resumable: only rows where embedding_v2 IS NULL are processed; primary legislation first.
Run inside the infohub-backend container, detached:
    nohup python /app/scripts/reembed_bge_m3.py >/tmp/reembed.log 2>&1 &
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from core.database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("reembed")

SELECT_BATCH = 256       # rows fetched + committed per loop
ENCODE_BATCH = 16        # bge-m3 encode sub-batch (CPU memory)


def main():
    logger.info("Loading BAAI/bge-m3 ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-m3")
    logger.info("Model loaded.")

    db = SessionLocal()
    try:
        total_remaining = db.execute(
            text("SELECT count(*) FROM document_chunks WHERE embedding_v2 IS NULL")
        ).scalar()
        grand_total = db.execute(text("SELECT count(*) FROM document_chunks")).scalar()
        logger.info(f"To embed: {total_remaining} / {grand_total} chunks")

        processed = 0
        start = time.time()
        while True:
            rows = db.execute(text("""
                SELECT c.id, c.content
                FROM document_chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.embedding_v2 IS NULL
                ORDER BY (CASE WHEN d.document_type IN ('law','regulation','guideline')
                               THEN 0 ELSE 1 END), c.id
                LIMIT :batch
            """), {"batch": SELECT_BATCH}).fetchall()
            if not rows:
                break

            contents = [(r[1] or " ") for r in rows]
            vectors = model.encode(
                contents, normalize_embeddings=True, batch_size=ENCODE_BATCH,
                show_progress_bar=False,
            )
            for (cid, _), vec in zip(rows, vectors):
                vec_str = "[" + ",".join(str(float(x)) for x in vec.tolist()) + "]"
                db.execute(
                    text("UPDATE document_chunks SET embedding_v2 = CAST(:v AS vector) WHERE id = :id"),
                    {"v": vec_str, "id": cid},
                )
            db.commit()

            processed += len(rows)
            if processed % (SELECT_BATCH * 4) == 0 or len(rows) < SELECT_BATCH:
                rate = processed / max(1e-6, time.time() - start)
                eta_h = (total_remaining - processed) / max(1e-6, rate) / 3600
                logger.info(f"  {processed}/{total_remaining} embedded | {rate:.1f}/s | ETA {eta_h:.1f}h")

        logger.info("All chunks embedded. Building HNSW index on embedding_v2 ...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS document_chunks_embedding_v2_idx
            ON document_chunks USING hnsw (embedding_v2 vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
        db.commit()
        done = db.execute(
            text("SELECT count(*) FROM document_chunks WHERE embedding_v2 IS NOT NULL")
        ).scalar()
        logger.info(f"DONE. embedding_v2 populated for {done}/{grand_total} chunks.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
