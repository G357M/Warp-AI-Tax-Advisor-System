from __future__ import annotations

from typing import Callable, Dict, List, Tuple
from .models import ParsedQuery, CandidateDocument
from .db_exact_lookup import (
    resolve_exact_from_backend,
    resolve_citation_from_backend,
    resolve_article_from_backend,
    resolve_point_from_backend,
)
from .db_metadata_lookup import search_metadata_from_backend


def bm25_candidates(parsed: ParsedQuery) -> List[CandidateDocument]:
    results: List[CandidateDocument] = []
    if parsed.topic == "property_tax":
        results.append(
            CandidateDocument(
                channel="bm25_search",
                document_id="7413ae69-672c-4c48-b3d5-8c04b09dfb43",
                title="საქართველოს საგადასახადო კოდექსი.",
                document_type="law",
                source_url="https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0",
                channel_score=0.72,
                why="matched lexical terms for property tax",
                metadata={
                    "topics": ["tax", "property_tax"],
                    "subjects": ["individual", "legal_entity"],
                    "goals": ["rate_lookup", "calculation_rule", "legal_basis"],
                    "authority_rank": 1.0,
                    "is_current": True,
                },
            )
        )
    return results


def semantic_candidates(parsed: ParsedQuery, limit: int = 5) -> List[CandidateDocument]:
    """Real cross-lingual chunk-level retrieval.

    Translates the query to Georgian (the cross-lingual gap) and runs a vector
    search over the corpus, returning the matched chunks so the answer can be
    grounded in the actual law text — not a generic document chunk or LLM memory.
    """
    query = parsed.normalized_query or parsed.raw_query
    if not query:
        return []
    try:
        from rag.pipeline import rag_pipeline
        retrieval_query = rag_pipeline._retrieval_query(query, parsed.language)
        embedding = rag_pipeline.embeddings.encode_query(retrieval_query)
        res = rag_pipeline.vector_store.search(query_embedding=embedding, n_results=limit)
    except Exception as exc:  # never break the pipeline on a retrieval issue
        print(f"[v2.semantic] retrieval error: {exc}")
        return []

    documents = res.get("documents", [[]])[0]
    metadatas = res.get("metadatas", [[]])[0]
    distances = res.get("distances", [[]])[0] or [None] * len(documents)

    results: List[CandidateDocument] = []
    for content, md, dist in zip(documents, metadatas, distances):
        md = md or {}
        similarity = round(max(1.0 - float(dist), 0.0), 4) if dist is not None else 0.0
        results.append(
            CandidateDocument(
                channel="semantic_search",
                document_id=str(md.get("document_id") or md.get("chunk_id") or ""),
                title=md.get("title") or "",
                document_type=md.get("document_type") or "law",
                source_url=md.get("source_url") or "",
                channel_score=similarity,
                why="cross-lingual semantic match (query translated to Georgian)",
                metadata={
                    "chunk_content": content,
                    "chunk_index": md.get("chunk_index"),
                    "similarity": similarity,
                    "topics": [parsed.topic] if parsed.topic else [],
                    "authority_rank": 0.8,
                    "is_current": True,
                },
            )
        )
    return results


CHANNEL_BUILDERS: Dict[str, Callable[[ParsedQuery], List[CandidateDocument]]] = {
    "exact_doc_resolver": resolve_exact_from_backend,
    "citation_resolver": resolve_citation_from_backend,
    "article_resolver": resolve_article_from_backend,
    "point_resolver": resolve_point_from_backend,
    "metadata_search": search_metadata_from_backend,
    "bm25_search": bm25_candidates,
    "semantic_search": semantic_candidates,
}


def _apply_channel_metadata(channel: str, items: List[CandidateDocument]) -> List[CandidateDocument]:
    for item in items:
        metadata = dict(item.metadata or {})
        retrieval_scores = dict(metadata.get("retrieval_scores", {}))
        retrieval_scores[channel] = round(item.channel_score, 4)

        metadata.update(
            {
                "source_class": item.document_type,
                "title_normalized": item.title.lower().strip(),
                "retrieval_origin": channel,
                "retrieval_scores": retrieval_scores,
                "retrieval_channels": sorted(set(metadata.get("retrieval_channels", []) + [channel])),
                "authority_rank": metadata.get("authority_rank", 0.0),
                "applicability_topics": metadata.get("topics", []),
                "applicability_subjects": metadata.get("subjects", []),
                "applicability_goals": metadata.get("goals", []),
                "matched_doc_number": metadata.get("document_number") or metadata.get("resolved_doc_number"),
                "matched_article_ref": metadata.get("article_ref"),
                "matched_point_ref": metadata.get("point_ref"),
                "chunk_metadata_version": "v2_candidate",
            }
        )
        item.metadata = metadata
    return items


def _ordered_channels(routing_profile: Dict[str, object] | None = None) -> List[Tuple[str, Callable[[ParsedQuery], List[CandidateDocument]]]]:
    channel_priority = dict((routing_profile or {}).get("channel_priority", {}))
    disabled = set((routing_profile or {}).get("disabled_channels", []))
    enabled = set((routing_profile or {}).get("enabled_channels", CHANNEL_BUILDERS.keys()))

    ranked = []
    for name, builder in CHANNEL_BUILDERS.items():
        if name in disabled or name not in enabled:
            continue
        ranked.append((channel_priority.get(name, 0), name, builder))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [(name, builder) for _, name, builder in ranked]


def generate_candidates(parsed: ParsedQuery, routing_profile: Dict[str, object] | None = None) -> Dict[str, List[CandidateDocument]]:
    results: Dict[str, List[CandidateDocument]] = {name: [] for name in CHANNEL_BUILDERS}

    for channel_name, builder in _ordered_channels(routing_profile):
        channel_items = _apply_channel_metadata(channel_name, builder(parsed))
        results[channel_name] = channel_items

        if (
            channel_name in {"exact_doc_resolver", "citation_resolver"}
            and channel_items
            and (routing_profile or {}).get("stop_on_exact")
        ):
            break

    return results
