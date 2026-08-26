#!/usr/bin/env python3
"""Build a complete public canary suite from legal-answer contracts.

Dry-run is the default and emits aggregate metadata only.  ``--output`` writes
the deterministic suite to a new file; an existing path is never overwritten.
The command performs no HTTP, database or LLM calls.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from rag_v2.faq_tax_matrix import build_tax_answer_contract_cases
from scripts.audit_legal_answer_contracts import audit_contracts


METRIC_THRESHOLDS = {
    "case_success_rate": 1.0,
    "http_success_rate": 1.0,
    "response_contract_accuracy": 1.0,
    "evidence_contract_accuracy": 1.0,
    "official_provision_link_accuracy": 1.0,
    "response_language_accuracy": 1.0,
    "min_language_case_success": 1.0,
}


def build_suite() -> dict[str, Any]:
    audit = audit_contracts()
    if audit["errors"]:
        raise ValueError("legal-answer contracts must pass audit before generation")
    cases = build_tax_answer_contract_cases()
    return {
        "schema_version": 1,
        "suite_version": f"legal-answer-contracts-{audit['contract_sha256'][:12]}",
        "description": (
            "Generated RU/EN/KA public-response contracts for deterministic "
            "tax guidance with exact official Matsne provision links."
        ),
        "contract_sha256": audit["contract_sha256"],
        "execution_profile": {
            "max_public_requests": len(cases),
            "request_interval_seconds": 8.0,
            "postgresql_writes_allowed": False,
            "redis_translation_cache_writes_allowed": True,
            "full_report_must_remain_operational": True,
        },
        "thresholds": dict(METRIC_THRESHOLDS),
        "cases": cases,
    }


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    if os.name != "nt":
        path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    suite = build_suite()
    summary = {
        "suite_version": suite["suite_version"],
        "contract_sha256": suite["contract_sha256"],
        "cases": len(suite["cases"]),
        "languages": ["ru", "en", "ka"],
        "required_max_public_requests": suite["execution_profile"]
        ["max_public_requests"],
        "request_interval_seconds": suite["execution_profile"]
        ["request_interval_seconds"],
        "network_calls_allowed": False,
        "database_calls_allowed": False,
        "llm_calls_allowed": False,
        "status": "written" if args.output else "dry_run",
    }
    if args.output:
        _write_new_json(args.output, suite)
        summary["output"] = str(args.output)
    print("LEGAL_ANSWER_CONTRACT_CANARY=" + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
