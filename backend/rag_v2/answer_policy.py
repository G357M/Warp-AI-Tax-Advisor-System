from __future__ import annotations

from typing import Dict
from .models import QuestionClassification


def build_answer_policy(classification: QuestionClassification, parsed_query: Dict[str, object] | None = None) -> Dict[str, object]:
    qc = classification.question_class
    parsed_query = parsed_query or {}
    has_article = bool(parsed_query.get("article_ref"))
    has_point = bool(parsed_query.get("point_ref"))

    if qc == "canonical_law_lookup":
        if has_point:
            return {
                "template": "canonical_point_v1",
                "response_strategy": [
                    "state the point directly",
                    "place it in the article structure",
                    "mention condition or exception",
                    "source reference",
                ],
                "should_include_warning": False,
                "should_request_clarification": False,
            }
        if has_article:
            return {
                "template": "canonical_article_v1",
                "response_strategy": [
                    "state the article directly",
                    "summarize the rule",
                    "mention important condition or exception",
                    "source reference",
                ],
                "should_include_warning": False,
                "should_request_clarification": False,
            }
        return {
            "template": "canonical_law_v1",
            "response_strategy": [
                "short conclusion",
                "legal norm",
                "important condition or exception",
                "source reference",
            ],
            "should_include_warning": False,
            "should_request_clarification": False,
        }

    if qc == "practical_tax_guidance":
        return {
            "template": "practical_guidance_v1",
            "response_strategy": [
                "practical conclusion",
                "how it is applied",
                "legal basis",
                "important caveat",
            ],
            "should_include_warning": False,
            "should_request_clarification": False,
        }

    if qc == "local_regulation_lookup":
        return {
            "template": "local_regulation_v1",
            "response_strategy": [
                "local answer",
                "named local act",
                "relation to general code",
                "freshness note",
            ],
            "should_include_warning": True,
            "should_request_clarification": False,
        }

    if qc == "dispute_practice":
        return {
            "template": "dispute_summary_v1",
            "response_strategy": [
                "practice summary",
                "reasoning used by authority or court",
                "norm relied on",
                "practical implication",
            ],
            "should_include_warning": False,
            "should_request_clarification": False,
        }

    if qc == "named_document_lookup":
        return {
            "template": "named_document_summary_v1",
            "response_strategy": [
                "identify the document",
                "say what it covers",
                "list main themes",
                "link the source",
            ],
            "should_include_warning": False,
            "should_request_clarification": False,
        }

    if qc == "amendment_tracking":
        return {
            "template": "amendment_tracking_v1",
            "response_strategy": [
                "what changed",
                "when",
                "by which act",
                "what applies now",
            ],
            "should_include_warning": False,
            "should_request_clarification": False,
        }

    return {
        "template": "generic_v1",
        "response_strategy": ["short answer"],
        "should_include_warning": True,
        "should_request_clarification": True,
    }
