#!/usr/bin/env python3
"""Audit parser-goal and legacy-guard coverage by legal answer contracts.

The audit is deterministic and read-only. It derives parser goals and remaining
hard-coded authoritative fact branches from the Python syntax tree, so adding a
new goal or curated legal answer without an explicit policy fails CI.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from rag_v2.faq_tax_matrix import TAX_FAQ_MATRIX
from rag_v2.legal_answer_contracts import LegalAnswerContract


PARSER_SOURCE_PATH = BACKEND_ROOT / "rag_v2" / "query_parser.py"
PUBLIC_RESPONSE_SOURCE_PATH = BACKEND_ROOT / "rag_v2" / "public_response.py"

CONTEXTUAL_RETRIEVAL_GOALS = {
    "amendment_tracking": "requires current amendment documents and dates",
    "calculation_rule": "requires query-specific facts and retrieved provisions",
    "dispute_outcome": "requires a named decision or dispute corpus evidence",
    "document_summary": "requires the requested source document",
}

# No authoritative legal fact may live outside the contract factory. Keeping
# this mapping explicit makes any future temporary exception a reviewed CI diff.
ALLOWED_HARDCODED_FACT_TOPICS: dict[str, str] = {}


def extract_parser_goals(source: str) -> set[str]:
    tree = ast.parse(source)
    goals: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "goal" for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            goals.add(node.value.value)
    return goals


def extract_hardcoded_fact_topics(source: str) -> set[str]:
    tree = ast.parse(source)
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_authoritative_tax_fact_impl"
        ),
        None,
    )
    if target is None:
        raise ValueError("_authoritative_tax_fact_impl was not found")

    def returned_topics(node: ast.AST) -> set[str]:
        topics: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Return):
                continue
            value = child.value.body if isinstance(child.value, ast.IfExp) else child.value
            if not isinstance(value, ast.Tuple) or len(value.elts) != 2:
                continue
            topic = value.elts[0]
            if isinstance(topic, ast.Constant) and isinstance(topic.value, str):
                topics.add(topic.value)
        return topics

    topics: set[str] = set()
    for node in target.body:
        branch_topics = returned_topics(node)
        delegates_to_contract = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "_contract_response_by_slug"
            for child in ast.walk(node)
        )
        if branch_topics and not delegates_to_contract:
            topics.update(branch_topics)
    return topics


def audit_coverage(
    contracts: Iterable[LegalAnswerContract] = TAX_FAQ_MATRIX,
    *,
    parser_source: str | None = None,
    public_response_source: str | None = None,
) -> dict[str, object]:
    selected = tuple(contracts)
    parser_source = parser_source or PARSER_SOURCE_PATH.read_text(encoding="utf-8")
    public_response_source = public_response_source or PUBLIC_RESPONSE_SOURCE_PATH.read_text(
        encoding="utf-8"
    )

    parser_goals = extract_parser_goals(parser_source)
    contract_goals = {
        goal for contract in selected for goal in contract.match_goals
    }
    contextual_goals = set(CONTEXTUAL_RETRIEVAL_GOALS)
    hardcoded_topics = extract_hardcoded_fact_topics(public_response_source)
    allowed_hardcoded = set(ALLOWED_HARDCODED_FACT_TOPICS)

    uncovered_goals = parser_goals - contract_goals - contextual_goals
    stale_contextual_goals = contextual_goals - parser_goals
    unexpected_hardcoded = hardcoded_topics - allowed_hardcoded
    stale_hardcoded_exceptions = allowed_hardcoded - hardcoded_topics

    errors = [
        *(f"uncovered parser goal: {goal}" for goal in sorted(uncovered_goals)),
        *(
            f"contextual goal policy is stale: {goal}"
            for goal in sorted(stale_contextual_goals)
        ),
        *(
            f"unexpected hard-coded authoritative fact: {topic}"
            for topic in sorted(unexpected_hardcoded)
        ),
        *(
            f"hard-coded fact exception is stale: {topic}"
            for topic in sorted(stale_hardcoded_exceptions)
        ),
    ]

    classified_goals = parser_goals & (contract_goals | contextual_goals)
    fingerprint_payload = {
        "parser_goals": sorted(parser_goals),
        "contract_goals": sorted(contract_goals & parser_goals),
        "contextual_goals": sorted(contextual_goals),
        "hardcoded_topics": sorted(hardcoded_topics),
        "hardcoded_exceptions": ALLOWED_HARDCODED_FACT_TOPICS,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "result": "pass" if not errors else "fail",
        "coverage_sha256": fingerprint,
        "parser_goal_count": len(parser_goals),
        "parser_goals": sorted(parser_goals),
        "contract_backed_goal_count": len(parser_goals & contract_goals),
        "contract_backed_goals": sorted(parser_goals & contract_goals),
        "contextual_retrieval_goal_count": len(contextual_goals),
        "contextual_retrieval_goals": sorted(contextual_goals),
        "classified_goal_coverage": (
            round(len(classified_goals) / len(parser_goals), 4)
            if parser_goals
            else 1.0
        ),
        "uncovered_goals": sorted(uncovered_goals),
        "legacy_hardcoded_fact_topics": sorted(hardcoded_topics),
        "allowed_hardcoded_fact_topics": sorted(allowed_hardcoded),
        "errors": errors,
        "error_count": len(errors),
        "network_calls_allowed": False,
        "database_calls_allowed": False,
        "llm_calls_allowed": False,
    }


def main() -> int:
    report = audit_coverage()
    print("LEGAL_ANSWER_COVERAGE_AUDIT=" + json.dumps(report, sort_keys=True))
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
