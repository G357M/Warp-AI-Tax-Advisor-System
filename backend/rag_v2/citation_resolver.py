from __future__ import annotations

import re
from typing import Dict, List

from .models import ParsedQuery, CandidateDocument


DOC_NUMBER_FIXTURES = {
    "1432": {
        "document_id": "property-guidance-1432",
        "title": "ქონების გადასახადის მიზნებისთვის მეუღლეთა შემოსავლის გაანგარიშება N1432",
        "document_type": "guideline",
        "source_url": "https://infohub.rs.ge/ka/workspace/document/4e025ee8-641e-4cc2-a284-3ecb8ac5972e",
    },
    "1433": {
        "document_id": "property-guidance-1433",
        "title": "მიწისა და მასზე განთავსებული შენობა-ნაგებობის დაბეგვრა ქონების გადასახადით N1433",
        "document_type": "guideline",
        "source_url": "https://infohub.rs.ge/ka/workspace/document/41e6c703-10ec-4d6e-aa01-d0e3f2e7afa5",
    },
    "19068/2/2023": {
        "document_id": "customs-dispute-19068-2-2023",
        "title": "გადაწყვეტილება №19068/2/2023",
        "document_type": "court_decision",
        "source_url": "https://infohub.rs.ge/ka/workspace/document/f8d0ca5b-2b73-4bc4-a09d-7e24d2121771",
    },
}


ARTICLE_PATTERNS = [
    re.compile(r"ст\.?\s*(\d+[¹²³\-\d]*)", re.IGNORECASE),
    re.compile(r"статья\s*(\d+[¹²³\-\d]*)", re.IGNORECASE),
    re.compile(r"article\s*(\d+[¹²³\-\d]*)", re.IGNORECASE),
    re.compile(r"მუხლი\s*(\d+[¹²³\-\d]*)", re.IGNORECASE),
    re.compile(r"(\d+(?:[¹²³]|-\d+)*)-?ე\s*მუხლ", re.IGNORECASE),
]

DOC_NUMBER_PATTERNS = [
    re.compile(r"(?:\b|^)n\s*(\d{3,}(?:/\d+/\d{4})?)\b", re.IGNORECASE),
    re.compile(r"№\s*(\d{3,}(?:/\d+/\d{4})?)", re.IGNORECASE),
    # bare number right after a document-type word: "ბრძანება 14640", "приказ 996"
    re.compile(
        r"(?:ბრძანებ\w*|დადგენილებ\w*|გადაწყვეტილებ\w*|приказ\w*|постановлени\w*|решени\w*|order|resolution|decision)"
        r"\s+(?:no\.?\s*)?(\d{3,}(?:/\d+/\d{4})?)\b",
        re.IGNORECASE,
    ),
]


def extract_citations(query: str) -> Dict[str, List[str]]:
    articles: List[str] = []
    doc_numbers: List[str] = []

    for pattern in ARTICLE_PATTERNS:
        articles.extend(pattern.findall(query))

    for pattern in DOC_NUMBER_PATTERNS:
        doc_numbers.extend(pattern.findall(query))

    return {
        "articles": list(dict.fromkeys(articles)),
        "doc_numbers": list(dict.fromkeys(doc_numbers)),
    }


def resolve_citations(parsed: ParsedQuery) -> List[CandidateDocument]:
    found = extract_citations(parsed.raw_query)
    results: List[CandidateDocument] = []

    for doc_number in found["doc_numbers"]:
        fixture = DOC_NUMBER_FIXTURES.get(doc_number)
        if not fixture:
            continue
        results.append(
                CandidateDocument(
                    channel="citation_resolver",
                    document_id=fixture["document_id"],
                title=fixture["title"],
                document_type=fixture["document_type"],
                source_url=fixture["source_url"],
                channel_score=0.98,
                    why=f"resolved explicit document number: {doc_number}",
                    metadata={
                        "resolved_doc_number": doc_number,
                        "resolved_articles": found["articles"],
                        "topics": ["property_tax"] if doc_number in {"1432", "1433"} else ["customs", "dispute"],
                        "subjects": ["individual"] if doc_number == "1432" else ["individual", "legal_entity"] if doc_number == "1433" else [],
                        "goals": ["document_summary", "calculation_rule"] if doc_number in {"1432", "1433"} else ["dispute_outcome"],
                        "authority_rank": 0.8 if doc_number in {"1432", "1433"} else 0.82,
                    },
                )
            )

    return results
