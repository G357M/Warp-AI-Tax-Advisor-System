from __future__ import annotations

from .models import ParsedQuery, QuestionClassification


CANONICAL_DOC_TITLES = [
    "customs clearance and customs control of goods",
]


def classify_query(parsed: ParsedQuery) -> QuestionClassification:
    q = parsed.normalized_query

    if parsed.point_ref or parsed.article_ref:
        return QuestionClassification(
            question_class="canonical_law_lookup",
            confidence=0.95,
            alternatives=[{"class": "named_document_lookup", "score": 0.35}],
            why=["explicit article or point reference detected"],
        )

    if "dispute" in parsed.signals and parsed.decision_ref:
        return QuestionClassification(
            question_class="dispute_practice",
            confidence=0.94,
            alternatives=[{"class": "named_document_lookup", "score": 0.7}],
            why=["explicit dispute markers and dispute decision reference detected"],
        )

    if parsed.document_ref or "named_document" in parsed.signals or any(token in q for token in CANONICAL_DOC_TITLES + ["n1432", "документ n"]):
        return QuestionClassification(
            question_class="named_document_lookup",
            confidence=0.9,
            alternatives=[],
            why=["named document signal detected"],
        )

    if "dispute" in parsed.signals:
        return QuestionClassification(
            question_class="dispute_practice",
            confidence=0.9,
            alternatives=[],
            why=["explicit dispute markers detected"],
        )

    if "amendment" in parsed.signals:
        return QuestionClassification(
            question_class="amendment_tracking",
            confidence=0.85,
            alternatives=[],
            why=["amendment markers detected"],
        )

    if parsed.locality and parsed.topic == "property_tax" and parsed.subject == "individual":
        return QuestionClassification(
            question_class="practical_tax_guidance",
            confidence=0.86,
            alternatives=[{"class": "local_regulation_lookup", "score": 0.74}],
            why=["individual property-tax query with locality needs practical guidance, not company-only local rate"],
        )

    if parsed.locality:
        return QuestionClassification(
            question_class="local_regulation_lookup",
            confidence=0.8,
            alternatives=[],
            why=["locality markers detected"],
        )

    if parsed.goal == "calculation_rule":
        return QuestionClassification(
            question_class="practical_tax_guidance",
            confidence=0.82,
            alternatives=[{"class": "canonical_law_lookup", "score": 0.58}],
            why=["practical calculation wording detected"],
        )

    return QuestionClassification(
        question_class="canonical_law_lookup",
        confidence=0.7,
        alternatives=[{"class": "practical_tax_guidance", "score": 0.45}],
        why=["defaulted to canonical law lookup"],
    )
