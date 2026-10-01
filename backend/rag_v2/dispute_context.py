"""Bounded same-document context for semantic matches on decision headings."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from core.database import SessionLocal
from models import DocumentChunk

logger = logging.getLogger(__name__)
MIN_CONTEXT_CHARACTERS = 300
MAX_CONTEXT_CHARACTERS = 6000


def expand_dispute_context(doc: dict, content: str, question_class: str) -> str:
    """Keep the matched text, adding at most three adjacent chunks from its decision.

    Only short semantic court-decision matches qualify. Statutory provision
    retrieval and existing substantive chunks retain their original boundaries.
    No text is generated, and missing/failed lookups retain the original match.
    """
    if question_class != "dispute_practice" or doc.get("document_type") != "court_decision":
        return content
    if not content or len(content.strip()) >= MIN_CONTEXT_CHARACTERS:
        return content
    index = (doc.get("metadata") or {}).get("chunk_index")
    if type(index) is not int or index < 0:
        return content
    try:
        document_id = UUID(str(doc.get("document_id")))
    except ValueError:
        return content
    try:
        with SessionLocal() as db:
            rows = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .filter(DocumentChunk.chunk_index >= max(0, index - 1),
                        DocumentChunk.chunk_index <= index + 2)
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(4)
                .all()
            )
    except SQLAlchemyError:
        logger.warning("Dispute context lookup failed; preserving matched chunk")
        return content
    return _join_context(rows, content, index)


def _join_context(rows, original: str, anchor: int) -> str:
    if not any(row.chunk_index == anchor for row in rows):
        return original
    # Reserve room for the anchor before admitting adjacent text; a large
    # previous chunk cannot consume the budget and displace the actual match.
    remaining = MAX_CONTEXT_CHARACTERS - len(original)
    selected = {anchor: original}
    for row in sorted(rows, key=lambda item: (abs(item.chunk_index - anchor), item.chunk_index)):
        text = (row.content or "").strip()
        if row.chunk_index == anchor or not text or len(text) + 2 > remaining:
            continue
        selected[row.chunk_index] = text
        remaining -= len(text) + 2
    return "\n\n".join(selected[index] for index in sorted(selected))
