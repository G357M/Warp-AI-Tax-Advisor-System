#!/usr/bin/env python3
"""Run a bounded public-API canary for exact official provision links.

Dry-run is the default. Execute mode is restricted to the backend loopback
public-query route and requires the exact request ceiling versioned in the
suite. Full answers and sources belong only in the selected operational report;
``--baseline-output`` emits aggregate fields safe for Git history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from rag_v2.official_provisions import is_official_provision_link


DEFAULT_SUITE_PATH = BACKEND_ROOT / "evaluation" / "public_provision_canary_set.json"
DEFAULT_URL = "http://127.0.0.1:8000/api/v1/public/query"

METRIC_NAMES = (
    "case_success_rate",
    "http_success_rate",
    "response_contract_accuracy",
    "evidence_contract_accuracy",
    "official_provision_link_accuracy",
    "response_language_accuracy",
    "min_language_case_success",
)

BASELINE_FIELDS = (
    "schema_version",
    "suite_version",
    "suite_sha256",
    "generated_at_utc",
    "deployed_commit",
    "endpoint_profile",
    "execution_profile",
    "cases",
    "passed_cases",
    "failed_cases",
    "request_budget",
    "metrics",
    "language_metrics",
    "failed_metrics",
)


def _validate_loopback_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port != 8000
        or parsed.path != "/api/v1/public/query"
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "public provision canary URL must be the backend loopback "
            "http://127.0.0.1:8000/api/v1/public/query route"
        )
    return value


def load_suite(path: Path = DEFAULT_SUITE_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_suite_payload(payload)


def validate_suite_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a static or generated canary suite without filesystem I/O."""
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported public provision canary schema_version")
    if not payload.get("suite_version"):
        raise ValueError("public provision canary suite_version is required")
    if set(payload.get("thresholds") or {}) != set(METRIC_NAMES):
        raise ValueError("public provision canary thresholds do not match metrics")

    profile = payload.get("execution_profile") or {}
    max_requests = profile.get("max_public_requests")
    if not isinstance(max_requests, int) or max_requests <= 0:
        raise ValueError("execution_profile.max_public_requests must be positive")
    request_interval = profile.get("request_interval_seconds")
    if not isinstance(request_interval, (int, float)) or request_interval < 8.0:
        raise ValueError(
            "execution_profile.request_interval_seconds must respect the "
            "10/minute guest rate limit with operational headroom"
        )
    if profile.get("postgresql_writes_allowed") is not False:
        raise ValueError("public provision canary must prohibit PostgreSQL writes")
    if profile.get("full_report_must_remain_operational") is not True:
        raise ValueError("full public provision report must remain operational")

    cases = payload.get("cases") or []
    ids = [case.get("id") for case in cases]
    if not cases or any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("public provision cases require unique non-empty ids")
    counts = {
        language: sum(case.get("language") == language for case in cases)
        for language in ("ru", "en", "ka")
    }
    if (
        not counts["ru"]
        or len(set(counts.values())) != 1
        or sum(counts.values()) != len(cases)
    ):
        raise ValueError(
            "public provision canary must contain a balanced non-empty "
            "RU/EN/KA case set"
        )
    if max_requests != len(cases):
        raise ValueError("max_public_requests must equal the versioned case count")

    for case in cases:
        provision = case.get("official_provision") or {}
        publication = urlparse(str(provision.get("verified_publication_url") or ""))
        if (
            not case.get("query")
            or not case.get("required_response_all")
            or not provision.get("article_ref")
            or not is_official_provision_link(
                {
                    "article_ref": provision.get("article_ref"),
                    "url": provision.get("url"),
                }
            )
            or publication.scheme != "https"
            or publication.hostname != "matsne.gov.ge"
            or publication.fragment
            or not parse_qs(publication.query).get("publication")
        ):
            raise ValueError(f"invalid public provision contract: {case.get('id')}")
    return payload


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def response_language_ok(language: str, text: str) -> bool:
    cleaned = re.sub(
        r"(?im)^\s*(?:source|источник|წყარო):.*$", "", text or ""
    ).strip()
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", cleaned))
    georgian = len(re.findall(r"[\u10A0-\u10FF]", cleaned))
    latin = len(re.findall(r"[A-Za-z]", cleaned))
    if language == "ru":
        return cyrillic >= 8 and georgian < 8
    if language == "en":
        return latin >= 8 and cyrillic < 8 and georgian < 8
    if language == "ka":
        return georgian >= 8 and cyrillic < 8
    return False


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                body = {"error": "non_json_success_response"}
            return {
                "http_status": response.status,
                "body": body,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            body = {"error": "non_json_http_error"}
        return {"http_status": exc.code, "body": body}
    except (OSError, TimeoutError) as exc:
        return {
            "http_status": None,
            "body": {},
            "transport_error": type(exc).__name__,
        }


def _source_matches_provision(
    source: dict[str, Any], expected: dict[str, Any]
) -> bool:
    metadata = source.get("metadata") or {}
    if not isinstance(metadata, dict):
        return False
    if (
        metadata.get("provision_publication_url")
        != expected["verified_publication_url"]
    ):
        return False
    candidates = (
        metadata.get("provision_links") or source.get("provision_links") or []
    )
    return any(
        isinstance(link, dict)
        and str(link.get("article_ref")) == expected["article_ref"]
        and link.get("url") == expected["url"]
        for link in candidates
    )


def score_case(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    http_status = response.get("http_status")
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    answer = str(body.get("response") or "").strip()
    sources = body.get("sources") if isinstance(body.get("sources"), list) else []
    evidence = body.get("evidence") if isinstance(body.get("evidence"), dict) else {}
    expected_evidence = case["evidence"]
    expected_provision = case["official_provision"]

    http_ok = http_status == 200
    response_contract_ok = bool(answer) and all(
        _normalize(item) in _normalize(answer)
        for item in case["required_response_all"]
    )
    source_count = int(evidence.get("source_count") or 0)
    evidence_contract_ok = (
        evidence.get("status") == expected_evidence["status"]
        and evidence.get("coverage") == expected_evidence["coverage"]
        and evidence.get("official_sources_only")
        == expected_evidence["official_sources_only"]
        and evidence.get("has_precise_citation")
        == expected_evidence["has_precise_citation"]
        and evidence.get("has_official_provision_link")
        == expected_evidence["has_official_provision_link"]
        and source_count >= expected_evidence["min_source_count"]
        and len(sources) >= expected_evidence["min_source_count"]
    )
    official_provision_link_ok = any(
        isinstance(source, dict)
        and _source_matches_provision(source, expected_provision)
        for source in sources
    )
    language_ok = response_language_ok(case["language"], answer)

    checks = {
        "http_ok": http_ok,
        "response_contract_ok": response_contract_ok,
        "evidence_contract_ok": evidence_contract_ok,
        "official_provision_link_ok": official_provision_link_ok,
        "response_language_ok": language_ok,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "id": case["id"],
        "language": case["language"],
        "query": case["query"],
        "http_status": http_status,
        "response": answer,
        "sources": sources,
        "evidence": evidence,
        "transport_error": response.get("transport_error"),
        **checks,
        "success": not failures,
        "failures": failures,
    }


def _ratio(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 1.0


def evaluate(
    suite: dict[str, Any],
    *,
    url: str,
    deployed_commit: str,
    max_public_requests: int,
    timeout: float,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    _validate_loopback_url(url)
    required_limit = suite["execution_profile"]["max_public_requests"]
    if max_public_requests != required_limit:
        raise ValueError("max_public_requests must match the versioned ceiling")

    results: list[dict[str, Any]] = []
    requests_made = 0
    for case in suite["cases"]:
        if requests_made >= max_public_requests:
            raise RuntimeError("public request budget exhausted")
        requests_made += 1
        result = _post_json(
            url,
            {"query": case["query"], "language": case["language"]},
            timeout,
        )
        if result.get("transport_error"):
            raise RuntimeError(
                "public canary loopback is unavailable; execute the canary "
                "inside the running backend container"
            )
        results.append(score_case(case, result))
        if requests_made < max_public_requests:
            time.sleep(suite["execution_profile"]["request_interval_seconds"])

    metrics = {
        "case_success_rate": _ratio(
            sum(item["success"] for item in results), len(results)
        ),
        "http_success_rate": _ratio(
            sum(item["http_ok"] for item in results), len(results)
        ),
        "response_contract_accuracy": _ratio(
            sum(item["response_contract_ok"] for item in results), len(results)
        ),
        "evidence_contract_accuracy": _ratio(
            sum(item["evidence_contract_ok"] for item in results), len(results)
        ),
        "official_provision_link_accuracy": _ratio(
            sum(item["official_provision_link_ok"] for item in results), len(results)
        ),
        "response_language_accuracy": _ratio(
            sum(item["response_language_ok"] for item in results), len(results)
        ),
    }
    language_metrics = {}
    for language in ("ru", "en", "ka"):
        selected = [item for item in results if item["language"] == language]
        language_metrics[language] = {
            "cases": len(selected),
            "case_success_rate": _ratio(
                sum(item["success"] for item in selected), len(selected)
            ),
        }
    metrics["min_language_case_success"] = min(
        item["case_success_rate"] for item in language_metrics.values()
    )
    failed_metrics = {
        name: {"actual": metrics[name], "required": suite["thresholds"][name]}
        for name in METRIC_NAMES
        if metrics[name] < suite["thresholds"][name]
    }
    generated_at = generated_at or datetime.now(timezone.utc)
    suite_bytes = json.dumps(
        suite, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "suite_version": suite["suite_version"],
        "suite_sha256": hashlib.sha256(suite_bytes).hexdigest(),
        "generated_at_utc": generated_at.astimezone(timezone.utc).isoformat(),
        "deployed_commit": deployed_commit,
        "endpoint_profile": {
            "transport": "loopback_http",
            "path": "/api/v1/public/query",
        },
        "execution_profile": suite["execution_profile"],
        "cases": len(results),
        "passed_cases": sum(item["success"] for item in results),
        "failed_cases": [
            {"id": item["id"], "failures": item["failures"]}
            for item in results
            if not item["success"]
        ],
        "request_budget": {
            "limit": max_public_requests,
            "actual": requests_made,
        },
        "metrics": metrics,
        "language_metrics": language_metrics,
        "failed_metrics": failed_metrics,
        "results": results,
    }


def baseline_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {key: report[key] for key in BASELINE_FIELDS}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-public-requests", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-output", type=Path)
    args = parser.parse_args()

    suite = load_suite(args.suite)
    required_limit = suite["execution_profile"]["max_public_requests"]
    if not args.execute:
        plan = {
            "suite_version": suite["suite_version"],
            "cases": len(suite["cases"]),
            "languages": ["ru", "en", "ka"],
            "required_max_public_requests": required_limit,
            "request_interval_seconds": suite["execution_profile"]
            ["request_interval_seconds"],
            "endpoint": "/api/v1/public/query",
            "postgresql_writes_allowed": False,
            "status": "dry_run",
        }
        print("PUBLIC_PROVISION_CANARY_PLAN=" + json.dumps(plan, sort_keys=True))
        return 0
    if args.max_public_requests != required_limit:
        parser.error(
            "--max-public-requests must exactly match the versioned suite ceiling "
            f"({required_limit})"
        )

    report = evaluate(
        suite,
        url=args.url,
        deployed_commit=args.commit,
        max_public_requests=args.max_public_requests,
        timeout=args.timeout,
    )
    if args.output:
        _write_json(args.output, report)
        print(f"Saved operational public provision report: {args.output}")
    if args.baseline_output:
        _write_json(args.baseline_output, baseline_summary(report))
        print(f"Saved aggregate public provision baseline: {args.baseline_output}")

    summary = {
        "suite_version": report["suite_version"],
        "deployed_commit": report["deployed_commit"],
        "cases": report["cases"],
        "passed_cases": report["passed_cases"],
        "request_budget": report["request_budget"],
        "metrics": report["metrics"],
        "failed_cases": report["failed_cases"],
        "failed_metrics": report["failed_metrics"],
    }
    print("PUBLIC_PROVISION_CANARY=" + json.dumps(summary, sort_keys=True))
    return 1 if report["failed_cases"] or report["failed_metrics"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
