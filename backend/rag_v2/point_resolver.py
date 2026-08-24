from __future__ import annotations

import re
from typing import Dict, List, Optional

from .models import ParsedQuery, CandidateDocument
from .named_legal_acts import match_named_article_act


POINT_FIXTURES: Dict[str, Dict[str, object]] = {
    "168.1": {
        "document_id": "7413ae69-672c-4c48-b3d5-8c04b09dfb43",
        "title": "საქართველოს საგადასახადო კოდექსი. მუხლი 168 პუნქტი 1",
        "document_type": "law",
        "source_url": "https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0",
        "chunk_hint": 121,
        "section_label": "მუხლი 168 პუნქტი 1",
    }
}

GENERIC_TAX_CODE_POINT = {
    "document_id": "7413ae69-672c-4c48-b3d5-8c04b09dfb43",
    "title": "საქართველოს საგადასახადო კოდექსი.",
    "document_type": "law",
    "source_url": "https://infohub.rs.ge/ka/workspace/document/800cbef0-32bf-4f06-94fe-8afd2bf144a0",
}


ARTICLE_NUMBER = r"\d+(?:[¹²³⁴⁵⁶⁷⁸⁹⁰]+|-\d+)?"


POINT_PATTERNS = [
    re.compile(
        rf"(?:\bст\.?|\bстатья|\barticle|\bart\.?)\s*({ARTICLE_NUMBER})"
        r"\s*\(\s*(\d+)\s*\)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"მუხლი\s*({ARTICLE_NUMBER})\s*\(\s*(\d+)\s*\)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"({ARTICLE_NUMBER})-?ე\s*მუხლ(?:ის|ში|ით)?"
        r"\s*\(\s*(\d+)\s*\)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bст\.?\s*({ARTICLE_NUMBER})\s*(?:п\.?|пункт)\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bстатья\s*({ARTICLE_NUMBER})\s*пункт\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bстатья\s*({ARTICLE_NUMBER})\s*(?:часть|ч\.)\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bст\.?\s*({ARTICLE_NUMBER})\s*(?:часть|ч\.)\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:\barticle|\bart\.?)\s*({ARTICLE_NUMBER})"
        r"\s*(?:point|paragraph)\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"მუხლი\s*({ARTICLE_NUMBER})\s*პუნქტი\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"({ARTICLE_NUMBER})-?ე\s*მუხლ(?:ის|ში|ით)?"
        r"\s*(\d+)-?ე\s*პუნქტ",
        re.IGNORECASE,
    ),
]


def extract_point_ref(raw_query: str) -> Optional[str]:
    for pattern in POINT_PATTERNS:
        match = pattern.search(raw_query)
        if match:
            return f"{match.group(1)}.{match.group(2)}"
    return None


def resolve_point(parsed: ParsedQuery) -> List[CandidateDocument]:
    point_ref = extract_point_ref(parsed.raw_query)
    if not point_ref:
        return []

    named_act = match_named_article_act(parsed)
    fixture = named_act or POINT_FIXTURES.get(point_ref)
    if not fixture and parsed.topic != "tax":
        return []

    if not fixture:
        article_ref, point_num = point_ref.split(".", 1)
        fixture = {
            **GENERIC_TAX_CODE_POINT,
            "section_label": f"მუხლი {article_ref} პუნქტი {point_num}",
        }

    return [
        CandidateDocument(
            channel="point_resolver",
            document_id=str(fixture["document_id"]),
            title=str(fixture["title"]),
            document_type=str(fixture["document_type"]),
            source_url=str(fixture["source_url"]),
            channel_score=0.995,
            why=f"resolved explicit point reference: {point_ref}",
            metadata={
                "point_ref": point_ref,
                "article_ref": point_ref.split(".", 1)[0],
                "chunk_hint": fixture.get("chunk_hint"),
                "section_label": fixture.get(
                    "section_label", f"მუხლი {point_ref.split('.', 1)[0]}"
                ),
                "topics": fixture.get(
                    "topics", [parsed.topic] if parsed.topic else []
                ),
                "authority_rank": 1.0,
                "is_current": True,
            },
        )
    ]
