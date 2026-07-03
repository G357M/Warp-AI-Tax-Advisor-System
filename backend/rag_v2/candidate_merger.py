from __future__ import annotations

from typing import Dict, List

from .models import CandidateDocument


CHANNEL_PRIORITY = {
    "exact_doc_resolver": 7,
    "point_resolver": 6,
    "article_resolver": 5,
    "citation_resolver": 4,
    "metadata_search": 3,
    "bm25_search": 2,
    "semantic_search": 1,
}


def _candidate_key(candidate: CandidateDocument) -> str:
    # semantic_search candidates carry a specific chunk of a document, not the
    # whole document -- when a large source document (e.g. the Tax Code) surfaces
    # several different chunks for one query, deduping them down to the document
    # id would silently keep only whichever chunk was processed last (no scoring
    # involved) and discard the rest before the reranker ever saw them. Key by
    # document+chunk instead so each chunk stays a separate candidate and the
    # reranker actually gets to choose the right one. Other channels genuinely
    # are one-candidate-per-document matches (citation/article/point/exact-doc
    # resolvers don't carry chunk text), so they keep the document-level key.
    if candidate.channel == "semantic_search" and candidate.document_id:
        chunk_index = (candidate.metadata or {}).get("chunk_index")
        if chunk_index is not None:
            return f"doc:{candidate.document_id}:chunk:{chunk_index}"
    if candidate.document_id:
        return f"doc:{candidate.document_id}"
    if candidate.source_url:
        return f"url:{candidate.source_url}"
    return f"title:{candidate.title.lower()}"


def merge_candidates(candidates_by_channel: Dict[str, List[CandidateDocument]]) -> Dict[str, List[CandidateDocument]]:
    merged_map: Dict[str, CandidateDocument] = {}

    for channel, items in candidates_by_channel.items():
        for item in items:
            key = _candidate_key(item)
            existing = merged_map.get(key)
            if existing is None:
                item.metadata = {
                    **item.metadata,
                    "merged_channels": [channel],
                    "best_channel": channel,
                    "best_channel_score": item.channel_score,
                }
                merged_map[key] = item
                continue

            existing_channels = list(existing.metadata.get("merged_channels", []))
            if channel not in existing_channels:
                existing_channels.append(channel)

            better_channel = CHANNEL_PRIORITY.get(channel, 0) > CHANNEL_PRIORITY.get(existing.metadata.get("best_channel"), 0)
            better_score = item.channel_score > float(existing.metadata.get("best_channel_score", existing.channel_score))

            existing.channel_score = max(existing.channel_score, item.channel_score)
            existing_retrieval_scores = dict(existing.metadata.get("retrieval_scores", {}))
            item_retrieval_scores = dict(item.metadata.get("retrieval_scores", {}))
            existing.metadata = {
                **existing.metadata,
                **item.metadata,
                "retrieval_scores": {
                    **existing_retrieval_scores,
                    **item_retrieval_scores,
                },
                "retrieval_channels": sorted(set(existing.metadata.get("retrieval_channels", []) + item.metadata.get("retrieval_channels", []))),
                "merged_channels": existing_channels,
                "best_channel": channel if better_channel else existing.metadata.get("best_channel", existing.channel),
                "best_channel_score": item.channel_score if better_score else existing.metadata.get("best_channel_score", existing.channel_score),
            }

            if better_channel:
                existing.channel = channel
                existing.why = f"{existing.why}; merged stronger channel: {channel}" if existing.why else f"merged stronger channel: {channel}"
            elif item.why:
                existing.why = f"{existing.why}; {item.why}" if existing.why else item.why

    return {
        "merged_candidates": list(merged_map.values())
    }
