from __future__ import annotations

from typing import Any, Dict, List
from .context_policy import filter_supporting_sources


def build_context_plan(reranking: Dict[str, Any], question_class: str | None = None) -> Dict[str, Any]:
    ranked = reranking.get("top_ranked_documents", [])
    primary = ranked[0] if ranked else None
    support_pool = ranked[1:10] if len(ranked) > 1 else []

    excluded_chunks: List[Dict[str, Any]] = []
    if question_class:
        filtered = filter_supporting_sources(question_class, support_pool)
        supporting = filtered["kept"][:3]
        excluded_chunks.extend(filtered["excluded"])
    else:
        supporting = support_pool[:3]

    included_chunks: List[Dict[str, Any]] = []
    if primary:
        primary_chunk = primary.get("metadata", {}).get("chunk_hint") if isinstance(primary.get("metadata"), dict) else None
        included_chunks.append({
            "document_id": primary.get("document_id"),
            "chunk_index": primary_chunk if primary_chunk is not None else 0,
            "reason": "primary citation chunk" if primary_chunk is not None else "primary source opening chunk",
        })
    for item in supporting:
        supporting_chunk = item.get("metadata", {}).get("chunk_hint") if isinstance(item.get("metadata"), dict) else None
        included_chunks.append({
            "document_id": item.get("document_id"),
            "chunk_index": supporting_chunk if supporting_chunk is not None else 0,
            "reason": "supporting citation chunk" if supporting_chunk is not None else "supporting source opening chunk",
        })

    return {
        "primary_source": primary,
        "supporting_sources": supporting,
        "included_chunks": included_chunks,
        "excluded_chunks": excluded_chunks,
        "context_length_chars": None,
    }
