from __future__ import annotations

from typing import Dict, List

from .models import ParsedQuery, CandidateDocument
from .named_legal_acts import match_named_article_act


ARTICLE_FIXTURES: Dict[str, Dict[str, object]] = {
    "168": {
        "document_id": "7413ae69-672c-4c48-b3d5-8c04b09dfb43",
        "title": "საქართველოს საგადასახადო კოდექსი. მუხლი 168",
        "document_type": "law",
        "source_url": "https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0",
        "chunk_hint": 120,
        "section_label": "მუხლი 168",
    },
    "12": {
        "document_id": "7413ae69-672c-4c48-b3d5-8c04b09dfb43",
        "title": "საქართველოს საგადასახადო კოდექსი. მუხლი 12",
        "document_type": "law",
        "source_url": "https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0",
        "chunk_hint": 18,
        "section_label": "მუხლი 12",
    },
}

GENERIC_TAX_CODE_ARTICLE = {
    "document_id": "7413ae69-672c-4c48-b3d5-8c04b09dfb43",
    "title": "საქართველოს საგადასახადო კოდექსი.",
    "document_type": "law",
    "source_url": "https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0",
}


def resolve_article(parsed: ParsedQuery) -> List[CandidateDocument]:
    if not parsed.article_ref:
        return []

    named_act = match_named_article_act(parsed)
    fixture = named_act or ARTICLE_FIXTURES.get(parsed.article_ref)
    if not fixture and parsed.topic != "tax":
        return []

    if not fixture:
        fixture = {
            **GENERIC_TAX_CODE_ARTICLE,
            "section_label": f"მუხლი {parsed.article_ref}",
        }

    return [
        CandidateDocument(
            channel="article_resolver",
            document_id=str(fixture["document_id"]),
            title=str(fixture["title"]),
            document_type=str(fixture["document_type"]),
            source_url=str(fixture["source_url"]),
            channel_score=0.99,
            why=f"resolved explicit article reference: {parsed.article_ref}",
            metadata={
                "article_ref": parsed.article_ref,
                "chunk_hint": fixture.get("chunk_hint"),
                "section_label": fixture.get(
                    "section_label", f"მუხლი {parsed.article_ref}"
                ),
                "topics": fixture.get(
                    "topics", [parsed.topic] if parsed.topic else []
                ),
                "authority_rank": 1.0,
                "is_current": True,
            },
        )
    ]
