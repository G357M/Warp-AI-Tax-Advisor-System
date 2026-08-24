from __future__ import annotations

from typing import List
from .models import ParsedQuery, CandidateDocument
from .named_legal_acts import GENERAL_ADMINISTRATIVE_CODE


CANONICAL_DOCS = [
    {
        **GENERAL_ADMINISTRATIVE_CODE,
    },
    {
        "aliases": [
            "customs clearance and customs control of goods",
            "customs control of goods",
            "dual use goods",
        ],
        "document_id": "ddcbd30f-a325-48ec-971a-922aa45a0b38",
        "title": "CUSTOMS CLEARANCE AND CUSTOMS CONTROL OF DUAL USE GOODS (GUAM countries) Handbook 2021-2023",
        "document_type": "guideline",
        "source_url": "https://infohub.rs.ge/ka/workspace/document/7fc0d360-9e3b-4ece-ab91-21c638cc77fc",
    },
    {
        "aliases": [
            "საგადასახადო კოდექსი",
            "налоговый кодекс грузии",
            "tax code of georgia",
            "georgian tax code",
        ],
        "document_id": "7413ae69-672c-4c48-b3d5-8c04b09dfb43",
        "title": "საქართველოს საგადასახადო კოდექსი.",
        "document_type": "law",
        "source_url": "https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0",
    },
]


def resolve_exact_documents(parsed: ParsedQuery) -> List[CandidateDocument]:
    if parsed.article_ref or parsed.point_ref:
        return []

    q = parsed.normalized_query
    results: List[CandidateDocument] = []
    for doc in CANONICAL_DOCS:
        if any(alias in q for alias in doc["aliases"]):
            results.append(
                CandidateDocument(
                    channel="exact_doc_resolver",
                    document_id=doc["document_id"],
                    title=doc["title"],
                    document_type=doc["document_type"],
                    source_url=doc["source_url"],
                    channel_score=1.0,
                    why="matched canonical alias",
                    metadata={
                        "aliases": doc["aliases"],
                        "topics": doc.get("topics")
                        or (
                            ["customs"]
                            if "customs" in doc["title"].lower()
                            else ["tax"]
                        ),
                        "subjects": ["individual", "legal_entity"] if doc["document_type"] == "law" else [],
                        "goals": ["document_summary", "legal_basis"],
                        "authority_rank": 1.0 if doc["document_type"] == "law" else 0.78,
                        "is_current": True,
                    },
                )
            )
    return results
