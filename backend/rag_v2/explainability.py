from __future__ import annotations

from typing import Any, Dict


def developer_view(trace: Dict[str, Any]) -> Dict[str, Any]:
    return trace


def expert_review_view(trace: Dict[str, Any]) -> Dict[str, Any]:
    reranking = trace.get("reranking", {})
    top_ranked = reranking.get("top_ranked_documents", [])[:5]
    return {
        "query": trace.get("query", {}),
        "classification": trace.get("classification", {}),
        "routing": trace.get("routing", {}),
        "top_documents": [
            {
                "title": d.get("title"),
                "document_type": d.get("document_type"),
                "final_score": d.get("final_score"),
                "why_selected": d.get("why_selected", []),
            }
            for d in top_ranked
        ],
        "primary_source": trace.get("context_assembly", {}).get("primary_source"),
        "source_audit": trace.get("source_audit", {}),
        "answer_policy": trace.get("answer_policy", {}),
    }


def human_summary_view(trace: Dict[str, Any]) -> Dict[str, Any]:
    classification = trace.get("classification", {})
    routing = trace.get("routing", {})
    primary = trace.get("context_assembly", {}).get("primary_source") or {}
    audit = trace.get("source_audit", {})
    return {
        "question_class": classification.get("question_class"),
        "why": classification.get("why", []),
        "retrieval_mode": routing.get("retrieval_mode"),
        "primary_source_title": primary.get("title"),
        "primary_source_type": primary.get("document_type"),
        "audit_passed": audit.get("passed"),
        "warnings": audit.get("warnings", []),
    }
