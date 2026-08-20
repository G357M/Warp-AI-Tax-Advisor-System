#!/usr/bin/env python
"""Export every unresolved decision-facts review candidate without writes.

The default action is a connected read-only plan. Materialization requires the
exact counts and source snapshot SHA-256 printed by that plan. The operational
report contains public document identifiers and URLs and must not enter Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT_PATH = (
    BACKEND_ROOT / "evaluation" / "decision_facts_expert_review_contract.json"
)
sys.path.insert(0, str(BACKEND_ROOT))

from rag_v2.db_utils import db_status, run_query  # noqa: E402


REVIEW_QUEUE_SQL = r"""
SELECT f.id::text AS facts_id, f.document_id::text, d.title, d.source_url,
       d.document_number, d.date_published, d.file_hash,
       char_length(coalesce(d.full_text, '')) AS content_length,
       md5(coalesce(d.full_text, '')) AS content_md5,
       md5(regexp_replace(coalesce(d.full_text, ''), '\s+', ' ', 'g'))
           AS normalized_content_md5,
       f.authority_body, f.dispute_type, f.outcome, f.in_favor,
       f.decision_number, f.decision_date, f.case_number,
       f.contested_articles, f.amount_gel,
       array_remove(ARRAY[
           CASE WHEN (f.outcome = 'satisfied' AND f.in_favor <> 'taxpayer')
                      OR (f.outcome = 'rejected' AND f.in_favor <> 'authority')
                      OR (f.outcome = 'partially_satisfied'
                          AND f.in_favor = 'authority')
                THEN 'outcome_alignment' END,
           CASE WHEN EXISTS (
               SELECT 1 FROM jsonb_array_elements_text(
                   CASE WHEN jsonb_typeof(f.contested_articles::jsonb) = 'array'
                        THEN f.contested_articles::jsonb ELSE '[]'::jsonb END
               ) article(value)
               WHERE article.value !~ %s
           ) THEN 'non_simple_article_reference' END,
           CASE WHEN f.outcome = 'unclear' THEN 'unclear_outcome' END
       ], NULL) AS queue_reasons
FROM decision_facts f
JOIN documents d ON d.id = f.document_id
WHERE (f.outcome = 'satisfied' AND f.in_favor <> 'taxpayer')
   OR (f.outcome = 'rejected' AND f.in_favor <> 'authority')
   OR (f.outcome = 'partially_satisfied' AND f.in_favor = 'authority')
   OR f.outcome = 'unclear'
   OR EXISTS (
       SELECT 1 FROM jsonb_array_elements_text(
           CASE WHEN jsonb_typeof(f.contested_articles::jsonb) = 'array'
                THEN f.contested_articles::jsonb ELSE '[]'::jsonb END
       ) article(value)
       WHERE article.value !~ %s
   )
ORDER BY f.document_id::text
"""


DUPLICATE_MEMBER_SQL = r"""
WITH base AS (
    SELECT f.id::text AS facts_id, f.document_id::text, d.title, d.source_url,
           d.document_number, d.date_published, d.file_hash,
           char_length(coalesce(d.full_text, '')) AS content_length,
           md5(coalesce(d.full_text, '')) AS content_md5,
           md5(regexp_replace(coalesce(d.full_text, ''), '\s+', ' ', 'g'))
               AS normalized_content_md5,
           f.authority_body, f.dispute_type, f.outcome, f.in_favor,
           f.decision_number, f.decision_date, f.case_number,
           regexp_replace(coalesce(f.decision_number, ''),
                          '[^0-9/-]', '', 'g') AS normalized_number
    FROM decision_facts f
    JOIN documents d ON d.id = f.document_id
), duplicate_keys AS (
    SELECT authority_body, normalized_number
    FROM base
    WHERE normalized_number <> ''
    GROUP BY authority_body, normalized_number
    HAVING count(*) > 1
)
SELECT b.*
FROM base b
JOIN duplicate_keys k
  ON k.authority_body IS NOT DISTINCT FROM b.authority_body
 AND k.normalized_number = b.normalized_number
ORDER BY b.authority_body, b.normalized_number, b.decision_date NULLS LAST,
         b.document_id
"""


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_safe,
    ).encode("utf-8")


def _json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def load_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not payload.get("contract_version"):
        raise ValueError("unsupported expert-review contract")
    profile = payload.get("execution_profile") or {}
    if profile.get("llm_calls_allowed") is not False:
        raise ValueError("expert-review export must prohibit LLM calls")
    if profile.get("postgresql_writes_allowed") is not False:
        raise ValueError("expert-review export must prohibit PostgreSQL writes")
    if profile.get("full_report_must_remain_operational") is not True:
        raise ValueError("full expert-review report must remain operational")
    pattern = payload.get("simple_article_reference_pattern")
    if not pattern:
        raise ValueError("simple article-reference pattern is required")
    re.compile(pattern)
    if set(payload.get("review_queues") or []) != {
        "outcome_alignment",
        "non_simple_article_reference",
        "unclear_outcome",
    }:
        raise ValueError("expert-review queues are incomplete")
    if set(payload.get("duplicate_candidate_classes") or []) != {
        "exact",
        "likely",
        "ambiguous",
    }:
        raise ValueError("duplicate candidate classes are incomplete")
    if set(payload.get("field_verdicts") or []) != {
        "correct",
        "incorrect",
        "not_applicable",
        "unable_to_verify",
    }:
        raise ValueError("field verdicts are incomplete")
    if set(payload.get("duplicate_verdicts") or []) != {
        "true_duplicate",
        "distinct_decisions",
        "mixed_group",
        "unable_to_verify",
    }:
        raise ValueError("duplicate verdicts are incomplete")
    return payload


def _normalized_title(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _distinct_nonempty(rows: list[dict[str, Any]], field: str) -> set[str]:
    return {str(row.get(field)) for row in rows if row.get(field) not in (None, "")}


def classify_duplicate_group(rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    if len(rows) < 2:
        raise ValueError("duplicate group requires at least two members")
    content_rows = [row for row in rows if int(row.get("content_length") or 0) > 0]
    content_hashes = _distinct_nonempty(content_rows, "content_md5")
    normalized_hashes = _distinct_nonempty(content_rows, "normalized_content_md5")
    source_urls = _distinct_nonempty(rows, "source_url")
    decision_dates = _distinct_nonempty(rows, "decision_date")
    normalized_titles = {_normalized_title(row.get("title")) for row in rows}
    normalized_titles.discard("")
    all_content_present = len(content_rows) == len(rows)
    all_sources_present = all(row.get("source_url") not in (None, "") for row in rows)
    all_dates_present = all(row.get("decision_date") not in (None, "") for row in rows)
    all_titles_present = all(_normalized_title(row.get("title")) for row in rows)

    signals = {
        "all_content_present": all_content_present,
        "same_content": all_content_present and len(content_hashes) == 1,
        "same_normalized_content": (
            all_content_present and len(normalized_hashes) == 1
        ),
        "same_source_url": all_sources_present and len(source_urls) == 1,
        "same_decision_date": all_dates_present and len(decision_dates) == 1,
        "same_normalized_title": all_titles_present and len(normalized_titles) == 1,
        "missing_decision_dates": sum(
            row.get("decision_date") in (None, "") for row in rows
        ),
    }
    if signals["same_content"]:
        classification = "exact"
    elif (
        signals["same_normalized_content"]
        or (signals["same_source_url"] and signals["same_decision_date"])
        or (signals["same_decision_date"] and signals["same_normalized_title"])
    ):
        classification = "likely"
    else:
        classification = "ambiguous"
    return classification, signals


def build_duplicate_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw_row in rows:
        row = {key: _json_safe(value) for key, value in raw_row.items()}
        key = (str(row.get("authority_body") or ""), str(row["normalized_number"]))
        grouped[key].append(row)

    groups = []
    for (authority_body, normalized_number), members in sorted(grouped.items()):
        members = sorted(members, key=lambda row: str(row["document_id"]))
        classification, signals = classify_duplicate_group(members)
        digest = hashlib.sha256(
            f"{authority_body}|{normalized_number}".encode("utf-8")
        ).hexdigest()[:16]
        groups.append(
            {
                "group_id": f"DFG-{digest.upper()}",
                "authority_body": authority_body or None,
                "normalized_number": normalized_number,
                "candidate_class": classification,
                "signals": signals,
                "member_count": len(members),
                "members": members,
            }
        )
    return groups


def build_export(
    contract: dict[str, Any], *, deployed_commit: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    backend = db_status()
    if backend.get("mode") != "db" or not backend.get("connectable"):
        raise RuntimeError(
            "expert-review export requires a connectable explicit DB URL"
        )
    pattern = contract["simple_article_reference_pattern"]
    review_rows = run_query(REVIEW_QUEUE_SQL, [pattern, pattern])
    duplicate_rows = run_query(DUPLICATE_MEMBER_SQL)
    review_items = [
        {key: _json_safe(value) for key, value in row.items()} for row in review_rows
    ]
    duplicate_groups = build_duplicate_groups(duplicate_rows)
    snapshot_payload = {
        "review_items": review_items,
        "duplicate_groups": duplicate_groups,
    }
    snapshot_sha256 = hashlib.sha256(_canonical_json(snapshot_payload)).hexdigest()
    contract_sha256 = hashlib.sha256(_canonical_json(contract)).hexdigest()
    queue_counts: dict[str, int] = defaultdict(int)
    for item in review_items:
        for reason in item.get("queue_reasons") or []:
            queue_counts[reason] += 1
    class_counts: dict[str, int] = defaultdict(int)
    for group in duplicate_groups:
        class_counts[group["candidate_class"]] += 1
    summary = {
        "contract_version": contract["contract_version"],
        "deployed_commit": deployed_commit,
        "snapshot_sha256": snapshot_sha256,
        "review_items": len(review_items),
        "review_queue_counts": dict(sorted(queue_counts.items())),
        "duplicate_groups": len(duplicate_groups),
        "duplicate_members": sum(group["member_count"] for group in duplicate_groups),
        "duplicate_class_counts": dict(sorted(class_counts.items())),
    }
    report = {
        "schema_version": 1,
        "report_type": "decision_facts_full_expert_review",
        "contract_version": contract["contract_version"],
        "contract_sha256": contract_sha256,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "deployed_commit": deployed_commit,
        "backend": {
            "mode": backend.get("mode"),
            "driver": backend.get("driver"),
            "connectable": backend.get("connectable"),
        },
        "execution_profile": contract["execution_profile"],
        "source_snapshot_sha256": snapshot_sha256,
        "counts": summary,
        "review_items": review_items,
        "duplicate_groups": duplicate_groups,
    }
    return report, summary


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError("output already exists; refusing to overwrite it")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, default=_json_safe)
        stream.write("\n")
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-review-items", type=int)
    parser.add_argument("--expected-duplicate-groups", type=int)
    parser.add_argument("--expected-duplicate-members", type=int)
    parser.add_argument("--expected-snapshot-sha256")
    args = parser.parse_args()

    contract = load_contract(args.contract)
    report, summary = build_export(contract, deployed_commit=args.commit)
    prefix = "DECISION_FACTS_EXPERT_REVIEW_EXPORT"
    if not args.execute:
        print(prefix + "_PLAN=" + json.dumps(summary, sort_keys=True))
        return 0

    required = {
        "--expected-review-items": args.expected_review_items,
        "--expected-duplicate-groups": args.expected_duplicate_groups,
        "--expected-duplicate-members": args.expected_duplicate_members,
    }
    for label, value in required.items():
        if value is None or value < 0:
            parser.error(f"{label} is required with --execute")
    if args.output is None:
        parser.error("--output is required with --execute")
    if not args.expected_snapshot_sha256:
        parser.error("--expected-snapshot-sha256 is required with --execute")
    expected_actual = (
        (args.expected_review_items, summary["review_items"], "review items"),
        (
            args.expected_duplicate_groups,
            summary["duplicate_groups"],
            "duplicate groups",
        ),
        (
            args.expected_duplicate_members,
            summary["duplicate_members"],
            "duplicate members",
        ),
    )
    for expected, actual, label in expected_actual:
        if expected != actual:
            raise ValueError(f"{label} changed: expected {expected}, got {actual}")
    if args.expected_snapshot_sha256.lower() != summary["snapshot_sha256"]:
        raise ValueError("expert-review source snapshot changed after dry run")

    _write_exclusive(args.output, report)
    print(
        prefix
        + "="
        + json.dumps({**summary, "output": str(args.output)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
