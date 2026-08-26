"""Small audited registry for explicit multilingual legal-act references."""

from __future__ import annotations

from typing import Any, Optional

from .models import ParsedQuery


GENERAL_ADMINISTRATIVE_CODE: dict[str, Any] = {
    "aliases": (
        "общий административный кодекс",
        "общего административного кодекс",
        "общем административном кодекс",
        "general administrative code",
        "ზოგადი ადმინისტრაციული კოდექს",
    ),
    "document_id": "3f33cb75-b642-477e-9265-661b04571e5a",
    "title": "საქართველოს ზოგადი ადმინისტრაციული კოდექსი",
    "document_type": "law",
    "source_url": "https://infohub.rs.ge/ka/workspace/document/8e288090-11dc-497e-a867-ff233c9d79e7",
    "topics": ["administrative_law", "administrative_appeal"],
}


CIVIL_CODE: dict[str, Any] = {
    "aliases": (
        "гражданский кодекс грузии",
        "гражданского кодекса грузии",
        "гражданском кодексе грузии",
        "гражданского кодекса",
        "гражданском кодексе",
        "civil code of georgia",
        "georgian civil code",
        "საქართველოს სამოქალაქო კოდექს",
    ),
    "document_id": "2d2f2e3c-78ce-49f1-94a6-b2580c0da1ef",
    "title": "საქართველოს სამოქალაქო კოდექსი",
    "document_type": "law",
    "source_url": "https://infohub.rs.ge/ka/workspace/document/1aa5b5a8-f2d6-4858-b2dc-642a4068bf98",
    "topics": ["civil_law", "contracts", "obligations"],
}


ENTREPRENEURS_LAW: dict[str, Any] = {
    "aliases": (
        "закон грузии о предпринимателях",
        "закона грузии о предпринимателях",
        "законе грузии о предпринимателях",
        "закон о предпринимателях",
        "закона о предпринимателях",
        "law of georgia on entrepreneurs",
        "law on entrepreneurs",
        "entrepreneurs law",
        "მეწარმეთა შესახებ",
    ),
    "document_id": "74d06788-7c76-420d-bb6c-0a79874dbc9e",
    "title": "მეწარმეთა შესახებ საქართველოს კანონი",
    "document_type": "law",
    "source_url": "https://infohub.rs.ge/ka/workspace/document/1f5a284f-9bf6-4109-afde-63d3afaeb09e",
    "topics": ["company_law", "corporate_governance", "conflict_of_interest"],
}


LABOUR_CODE: dict[str, Any] = {
    "aliases": (
        "трудовой кодекс грузии",
        "трудового кодекса грузии",
        "трудовом кодексе грузии",
        "трудовой кодекс",
        "трудового кодекса",
        "labour code of georgia",
        "labor code of georgia",
        "georgian labour code",
        "georgian labor code",
        "labour code",
        "labor code",
        "საქართველოს შრომის კოდექს",
        "შრომის კოდექს",
    ),
    "document_id": "a24ab0d4-4124-414e-aa99-b526839abdd3",
    "title": "საქართველოს შრომის კოდექსი",
    "document_type": "law",
    "source_url": "https://infohub.rs.ge/ka/workspace/document/c16095a8-2c94-4024-8d25-561192e0ceb7",
    "topics": ["employment_law", "employment_contracts", "termination"],
}


ORDER_996: dict[str, Any] = {
    "document_id": "54d15b6c-e8a1-465a-bc56-8c20498588b8",
    "title": "გადასახადების ადმინისტრირების შესახებ.",
    "document_type": "regulation",
    "source_url": "https://infohub.rs.ge/ka/workspace/document/fe1cc7b3-a080-4283-85dd-ea9c9f85d947",
    "topics": ["tax_administration"],
}


def match_named_article_act(parsed: ParsedQuery) -> Optional[dict[str, Any]]:
    query = str(parsed.normalized_query or parsed.raw_query or "").lower()
    if any(alias in query for alias in GENERAL_ADMINISTRATIVE_CODE["aliases"]):
        return GENERAL_ADMINISTRATIVE_CODE
    if any(alias in query for alias in CIVIL_CODE["aliases"]):
        return CIVIL_CODE
    if any(alias in query for alias in ENTREPRENEURS_LAW["aliases"]):
        return ENTREPRENEURS_LAW
    if any(alias in query for alias in LABOUR_CODE["aliases"]):
        return LABOUR_CODE
    return None


def exact_reference_metadata(parsed: ParsedQuery) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if parsed.point_ref:
        article_ref = parsed.point_ref.split(".", 1)[0]
        metadata.update(
            {
                "article_ref": article_ref,
                "point_ref": parsed.point_ref,
                "section_label": f"მუხლი {article_ref}",
            }
        )
    elif parsed.article_ref:
        metadata.update(
            {
                "article_ref": parsed.article_ref,
                "section_label": f"მუხლი {parsed.article_ref}",
            }
        )
    return metadata
