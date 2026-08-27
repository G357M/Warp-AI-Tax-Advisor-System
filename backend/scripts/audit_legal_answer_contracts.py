#!/usr/bin/env python3
"""Audit the generated multilingual legal-answer contract factory.

This command is deterministic and read-only.  It makes no HTTP, database or
LLM calls and emits only aggregate diagnostics plus a content fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable


BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from rag_v2.faq_tax_matrix import TAX_FAQ_MATRIX
from rag_v2.legal_answer_contracts import (
    SUPPORTED_LANGUAGES,
    LegalAnswerContract,
    build_contract_cases,
    canonical_article_ref,
)
from rag_v2.official_provisions import load_official_provision_registries


def _fingerprint(contracts: Iterable[LegalAnswerContract]) -> str:
    payload = [
        {
            "slug": item.slug,
            "topic": item.topic,
            "subject": item.subject,
            "question_class": item.question_class,
            "response_kind": item.response_kind,
            "match_goals": item.match_goals,
            "registry_id": item.registry_id,
            "article_refs": item.article_refs,
            "sample_queries": item.sample_queries,
            "response_by_lang": item.response_by_lang,
            "smoke_contains": item.smoke_contains,
            "note": item.note,
        }
        for item in contracts
    ]
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def audit_contracts(
    contracts: Iterable[LegalAnswerContract] = TAX_FAQ_MATRIX,
) -> dict[str, Any]:
    selected = list(contracts)
    errors: list[str] = []
    slugs = [item.slug for item in selected]
    if len(slugs) != len(set(slugs)):
        errors.append("contract slugs must be unique")
    signatures: set[tuple[str, str, str, str | None]] = set()
    for contract in selected:
        if not contract.match_goals:
            errors.append(f"{contract.slug}: at least one match goal is required")
        for goal in contract.match_goals:
            signature = (
                contract.topic,
                contract.question_class,
                goal,
                contract.subject,
            )
            if signature in signatures:
                errors.append(
                    f"{contract.slug}: duplicate deterministic match signature {signature}"
                )
            signatures.add(signature)

    registries = {
        item["registry_id"]: item for item in load_official_provision_registries()
    }
    verified_articles = 0
    localized_answers = 0
    for contract in selected:
        if canonical_article_ref(contract.article_ref) != contract.article_ref:
            errors.append(f"{contract.slug}: primary article_ref is not canonical")
        registry = registries.get(contract.registry_id)
        if registry is None:
            errors.append(f"{contract.slug}: unknown registry {contract.registry_id}")
            continue
        for article_ref in contract.article_refs:
            has_locator = (
                article_ref in registry.get("article_anchors", {})
                or article_ref in registry.get("article_links", {})
            )
            if not has_locator:
                errors.append(
                    f"{contract.slug}: article {article_ref} has no verified locator"
                )
            else:
                verified_articles += 1
        for language in SUPPORTED_LANGUAGES:
            localized_answers += 1
            if not contract.sample_queries.get(language):
                errors.append(f"{contract.slug}/{language}: missing sample query")
            if not contract.response_by_lang.get(language):
                errors.append(f"{contract.slug}/{language}: missing response")
                continue
            response = contract.response(language)
            for token in (contract.smoke_contains or {}).get(language) or []:
                if token not in response:
                    errors.append(
                        f"{contract.slug}/{language}: missing required token {token!r}"
                    )
            if contract.citation(language) not in response:
                errors.append(
                    f"{contract.slug}/{language}: generated citation is missing"
                )

    generated_cases = []
    try:
        generated_cases = build_contract_cases(selected)
    except ValueError as exc:
        errors.append(str(exc))

    expected_cases = len(selected) * len(SUPPORTED_LANGUAGES)
    if len(generated_cases) != expected_cases:
        errors.append(
            f"generated case count {len(generated_cases)} != expected {expected_cases}"
        )

    return {
        "schema_version": 1,
        "contracts": len(selected),
        "localized_answers": localized_answers,
        "generated_cases": len(generated_cases),
        "languages": list(SUPPORTED_LANGUAGES),
        "verified_article_bindings": verified_articles,
        "contract_sha256": _fingerprint(selected),
        "error_count": len(errors),
        "errors": errors,
        "result": "pass" if not errors else "fail",
        "network_calls_allowed": False,
        "database_calls_allowed": False,
        "llm_calls_allowed": False,
    }


def main() -> int:
    report = audit_contracts()
    print("LEGAL_ANSWER_CONTRACT_AUDIT=" + json.dumps(report, sort_keys=True))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
