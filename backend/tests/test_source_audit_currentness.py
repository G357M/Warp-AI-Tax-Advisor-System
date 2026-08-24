from rag_v2.models import ParsedQuery, QuestionClassification
from rag_v2.source_audit import audit_sources


def test_noncurrent_primary_law_fails_currentness_contract():
    audit = audit_sources(
        ParsedQuery(raw_query="VAT rate", topic="vat", goal="rate_lookup"),
        QuestionClassification(question_class="canonical_law_lookup"),
        {
            "top_ranked_documents": [
                {
                    "document_type": "law",
                    "metadata": {"article_ref": "166", "is_current": False},
                }
            ]
        },
    )

    assert audit["passed"] is False
    assert audit["checks"]["current_source_consistency"] is False
    assert "not marked current" in " ".join(audit["warnings"])


def test_unknown_currentness_is_not_falsely_reported_as_outdated():
    audit = audit_sources(
        ParsedQuery(raw_query="Article 166", article_ref="166"),
        QuestionClassification(question_class="canonical_law_lookup"),
        {"top_ranked_documents": [{"document_type": "law", "metadata": {}}]},
    )

    assert audit["passed"] is True
    assert audit["checks"]["current_source_consistency"] is True
