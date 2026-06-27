from __future__ import annotations

from .models import ParsedQuery, CandidateDocument


def specificity_score(parsed: ParsedQuery, candidate: CandidateDocument) -> float:
    hay = (candidate.title + " " + (candidate.why or "")).lower()
    score = 0.0

    if parsed.subject == "individual" and any(token in hay for token in ["ფიზიკური", "physical person", "физичес", "spouse", "მეუღლ"]):
        score += 0.08

    if parsed.goal == "calculation_rule" and any(token in hay for token in ["გაანგარიშ", "расчет", "calculation", "income", "შემოსავ"]):
        score += 0.08

    if parsed.topic == "property_tax" and any(token in hay for token in ["ქონების გადასახად", "налог на имущество", "property tax"]):
        score += 0.06

    if parsed.goal == "document_summary" and candidate.channel == "exact_doc_resolver":
        score += 0.04

    return round(score, 4)
