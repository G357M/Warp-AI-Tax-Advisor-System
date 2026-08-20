#!/usr/bin/env python
"""Evaluate decision_facts quality without LLM calls or database writes.

The aggregate baseline is safe for Git. The full report additionally contains
public document identifiers/URLs for human legal review and must remain an
operational artifact with restricted permissions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT_PATH = (
    BACKEND_ROOT / "evaluation" / "decision_facts_quality_contract.json"
)
sys.path.insert(0, str(BACKEND_ROOT))

from decision_fact_contract import EXTRACTION_VERSION  # noqa: E402
from rag_v2.db_utils import db_status, run_query  # noqa: E402


METRIC_NAMES = (
    "fact_coverage_rate",
    "current_extraction_rate",
    "structural_integrity_rate",
    "positive_amount_rate",
    "outcome_alignment_rate",
    "prior_reference_safety_rate",
    "simple_article_reference_rate",
    "appeal_link_integrity_rate",
)

BASELINE_FIELDS = (
    "schema_version",
    "contract_version",
    "contract_sha256",
    "generated_at_utc",
    "deployed_commit",
    "backend",
    "execution_profile",
    "corpus",
    "counts",
    "metrics",
    "failed_metrics",
    "review_queue_counts",
    "distributions",
)

QUALITY_SQL = r"""
WITH eligible_docs AS (
    SELECT id
    FROM documents
    WHERE document_type = 'court_decision'
      AND (metadata->>'kind') IS DISTINCT FROM 'digest'
),
facts AS (
    SELECT f.*, d.id AS joined_document_id, d.document_type AS joined_document_type,
           d.metadata->>'kind' AS joined_kind
    FROM decision_facts f
    LEFT JOIN documents d ON d.id = f.document_id
)
SELECT
    (SELECT count(*) FROM eligible_docs) AS eligible_documents,
    (SELECT count(*) FROM decision_facts) AS facts_total,
    (SELECT count(*) FROM eligible_docs e JOIN decision_facts f ON f.document_id=e.id)
        AS covered_documents,
    count(*) FILTER (WHERE extraction_version = %s) AS current_version_rows,
    count(*) FILTER (WHERE
        joined_document_id IS NULL
        OR joined_document_type IS DISTINCT FROM 'court_decision'
        OR joined_kind = 'digest'
        OR raw_json IS NULL
        OR model IS NULL OR btrim(model) = ''
        OR authority_body IS NULL OR authority_body NOT IN (
            'revenue_service_council', 'mof_dispute_council', 'city_court',
            'appeals_court', 'supreme_court', 'other'
        )
        OR dispute_type IS NULL OR dispute_type NOT IN ('tax', 'customs', 'both', 'other')
        OR outcome IS NULL OR outcome NOT IN (
            'satisfied', 'partially_satisfied', 'rejected', 'unclear'
        )
        OR in_favor IS NULL OR in_favor NOT IN (
            'taxpayer', 'authority', 'partial', 'unclear'
        )
        OR (contested_articles IS NOT NULL
            AND jsonb_typeof(contested_articles::jsonb) <> 'array')
        OR (prior_refs IS NOT NULL AND jsonb_typeof(prior_refs::jsonb) <> 'array')
    ) AS structural_issue_rows,
    count(amount_gel) AS amount_rows,
    count(*) FILTER (WHERE amount_gel > 0) AS positive_amount_rows,
    count(*) FILTER (WHERE amount_gel IS NOT NULL AND amount_gel <= 0)
        AS nonpositive_amount_rows,
    count(*) FILTER (WHERE
        (outcome = 'satisfied' AND in_favor <> 'taxpayer')
        OR (outcome = 'rejected' AND in_favor <> 'authority')
        OR (outcome = 'partially_satisfied' AND in_favor = 'authority')
    ) AS outcome_alignment_issue_rows,
    count(*) FILTER (WHERE EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(prior_refs::jsonb) = 'array'
                 THEN prior_refs::jsonb ELSE '[]'::jsonb END
        ) ref(value)
        WHERE regexp_replace(coalesce(ref.value->>'number', ''), '[^0-9/-]', '', 'g') <> ''
          AND regexp_replace(coalesce(ref.value->>'number', ''), '[^0-9/-]', '', 'g') =
              regexp_replace(coalesce(decision_number, ''), '[^0-9/-]', '', 'g')
    )) AS self_prior_reference_rows,
    count(*) FILTER (WHERE CASE
        WHEN jsonb_typeof(contested_articles::jsonb) = 'array'
        THEN jsonb_array_length(contested_articles::jsonb) > 0
        ELSE false END)
        AS article_rows,
    count(*) FILTER (WHERE EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(contested_articles::jsonb) = 'array'
                 THEN contested_articles::jsonb ELSE '[]'::jsonb END
        ) a(value)
        WHERE a.value !~ %s
    )) AS non_simple_article_rows,
    count(*) FILTER (WHERE decision_number IS NULL OR btrim(decision_number) = '')
        AS missing_decision_number_rows,
    count(*) FILTER (WHERE decision_date IS NULL) AS missing_decision_date_rows,
    count(*) FILTER (WHERE outcome = 'unclear') AS unclear_outcome_rows,
    count(*) FILTER (WHERE extraction_version < %s) AS outdated_extraction_rows,
    max(created_at) AS latest_fact_created_at,
    (
        SELECT count(*) FROM (
            SELECT authority_body,
                   regexp_replace(decision_number, '[^0-9/-]', '', 'g') AS normalized_number
            FROM decision_facts
            WHERE decision_number IS NOT NULL
              AND regexp_replace(decision_number, '[^0-9/-]', '', 'g') <> ''
            GROUP BY authority_body, regexp_replace(decision_number, '[^0-9/-]', '', 'g')
            HAVING count(*) > 1
        ) duplicate_groups
    ) AS duplicate_identity_groups
FROM facts
"""

LINK_SQL = r"""
SELECT
    count(*) AS links_total,
    count(*) FILTER (WHERE
        hi.id IS NULL OR lo.id IS NULL
        OR l.from_facts_id = l.to_facts_id
        OR l.method NOT IN ('prior_ref', 'case_number')
        OR l.confidence < 0 OR l.confidence > 1
        OR (hi.decision_date IS NOT NULL AND lo.decision_date IS NOT NULL
            AND lo.decision_date > hi.decision_date)
        OR (CASE hi.authority_body
                WHEN 'revenue_service_council' THEN 1
                WHEN 'mof_dispute_council' THEN 2
                WHEN 'city_court' THEN 3
                WHEN 'appeals_court' THEN 4
                WHEN 'supreme_court' THEN 5 ELSE 0 END)
           <=
           (CASE lo.authority_body
                WHEN 'revenue_service_council' THEN 1
                WHEN 'mof_dispute_council' THEN 2
                WHEN 'city_court' THEN 3
                WHEN 'appeals_court' THEN 4
                WHEN 'supreme_court' THEN 5 ELSE 0 END)
    ) AS invalid_link_rows,
    count(*) FILTER (WHERE l.method = 'prior_ref') AS prior_ref_links,
    count(*) FILTER (WHERE l.method = 'case_number') AS case_number_links
FROM decision_links l
LEFT JOIN decision_facts hi ON hi.id = l.from_facts_id
LEFT JOIN decision_facts lo ON lo.id = l.to_facts_id
"""

DISTRIBUTION_SQL = """
SELECT authority_body, dispute_type, outcome, in_favor, count(*) AS count
FROM decision_facts
GROUP BY authority_body, dispute_type, outcome, in_favor
ORDER BY authority_body, dispute_type, outcome, in_favor
"""

STRATIFIED_REVIEW_SQL = """
WITH ranked AS (
    SELECT f.document_id::text, d.title, d.source_url,
           f.authority_body, f.dispute_type, f.outcome, f.in_favor,
           f.decision_number, f.decision_date, f.contested_articles,
           (f.amount_gel IS NOT NULL) AS has_amount,
           row_number() OVER (
               PARTITION BY f.authority_body, f.outcome
               ORDER BY md5(f.document_id::text || %s)
           ) AS sample_rank
    FROM decision_facts f
    JOIN documents d ON d.id = f.document_id
    WHERE f.authority_body IS DISTINCT FROM 'other'
)
SELECT * FROM ranked WHERE sample_rank <= %s
ORDER BY authority_body, outcome, sample_rank
"""

ANOMALY_REVIEW_SQL = r"""
WITH flagged AS (
    SELECT f.document_id::text, d.title, d.source_url,
           f.authority_body, f.dispute_type, f.outcome, f.in_favor,
           f.decision_number, f.decision_date,
           array_remove(ARRAY[
               CASE WHEN f.extraction_version < %s THEN 'outdated_extraction' END,
               CASE WHEN f.amount_gel IS NOT NULL AND f.amount_gel <= 0
                    THEN 'nonpositive_amount' END,
               CASE WHEN (f.outcome = 'satisfied' AND f.in_favor <> 'taxpayer')
                          OR (f.outcome = 'rejected' AND f.in_favor <> 'authority')
                          OR (f.outcome = 'partially_satisfied' AND f.in_favor = 'authority')
                    THEN 'outcome_alignment' END,
               CASE WHEN EXISTS (
                   SELECT 1 FROM jsonb_array_elements(
                       CASE WHEN jsonb_typeof(f.prior_refs::jsonb) = 'array'
                            THEN f.prior_refs::jsonb ELSE '[]'::jsonb END
                   ) ref(value)
                   WHERE regexp_replace(coalesce(ref.value->>'number', ''),
                                        '[^0-9/-]', '', 'g') <> ''
                     AND regexp_replace(coalesce(ref.value->>'number', ''),
                                        '[^0-9/-]', '', 'g') =
                         regexp_replace(coalesce(f.decision_number, ''),
                                        '[^0-9/-]', '', 'g')
               ) THEN 'self_prior_reference' END,
               CASE WHEN EXISTS (
                   SELECT 1 FROM jsonb_array_elements_text(
                       CASE WHEN jsonb_typeof(f.contested_articles::jsonb) = 'array'
                            THEN f.contested_articles::jsonb ELSE '[]'::jsonb END
                   ) a(value) WHERE a.value !~ %s
               ) THEN 'non_simple_article_reference' END
           ], NULL) AS anomaly_flags
    FROM decision_facts f
    JOIN documents d ON d.id = f.document_id
)
SELECT * FROM flagged
WHERE cardinality(anomaly_flags) > 0
ORDER BY md5(document_id || %s)
LIMIT %s
"""


def load_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported decision-facts contract schema_version")
    if not payload.get("contract_version"):
        raise ValueError("decision-facts contract_version is required")
    if payload.get("expected_extraction_version") != EXTRACTION_VERSION:
        raise ValueError("decision-facts expected extraction version is stale")
    if set(payload.get("thresholds") or {}) != set(METRIC_NAMES):
        raise ValueError("decision-facts thresholds do not match evaluator metrics")
    profile = payload.get("execution_profile") or {}
    if profile.get("llm_calls_allowed") is not False:
        raise ValueError("decision-facts quality audit must prohibit LLM calls")
    if profile.get("postgresql_writes_allowed") is not False:
        raise ValueError("decision-facts quality audit must prohibit PostgreSQL writes")
    pattern = payload.get("simple_article_reference_pattern")
    if not pattern:
        raise ValueError("simple article-reference pattern is required")
    re.compile(pattern)
    if int(payload.get("review_sample_per_stratum") or 0) <= 0:
        raise ValueError("review_sample_per_stratum must be positive")
    if int(payload.get("max_anomaly_review_items") or 0) <= 0:
        raise ValueError("max_anomaly_review_items must be positive")
    return payload


def _ratio(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 1.0


def calculate_metrics(
    quality: dict[str, Any], links: dict[str, Any]
) -> dict[str, float]:
    facts = int(quality["facts_total"])
    amounts = int(quality["amount_rows"])
    article_rows = int(quality["article_rows"])
    link_count = int(links["links_total"])
    return {
        "fact_coverage_rate": _ratio(
            int(quality["covered_documents"]), int(quality["eligible_documents"])
        ),
        "current_extraction_rate": _ratio(
            int(quality["current_version_rows"]), facts
        ),
        "structural_integrity_rate": _ratio(
            facts - int(quality["structural_issue_rows"]), facts
        ),
        "positive_amount_rate": _ratio(
            int(quality["positive_amount_rows"]), amounts
        ),
        "outcome_alignment_rate": _ratio(
            facts - int(quality["outcome_alignment_issue_rows"]), facts
        ),
        "prior_reference_safety_rate": _ratio(
            facts - int(quality["self_prior_reference_rows"]), facts
        ),
        "simple_article_reference_rate": _ratio(
            article_rows - int(quality["non_simple_article_rows"]), article_rows
        ),
        "appeal_link_integrity_rate": _ratio(
            link_count - int(links["invalid_link_rows"]), link_count
        ),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def evaluate(
    contract: dict[str, Any],
    *,
    deployed_commit: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    backend = db_status()
    if backend.get("mode") != "db" or not backend.get("connectable"):
        raise RuntimeError(
            "decision-facts evaluation requires db mode and a connectable explicit URL"
        )
    pattern = contract["simple_article_reference_pattern"]
    version = contract["expected_extraction_version"]
    quality_rows = run_query(QUALITY_SQL, [version, pattern, version])
    link_rows = run_query(LINK_SQL)
    if len(quality_rows) != 1 or len(link_rows) != 1:
        raise RuntimeError("decision-facts aggregate query returned an unexpected shape")
    quality = {key: _json_safe(value) for key, value in quality_rows[0].items()}
    links = {key: _json_safe(value) for key, value in link_rows[0].items()}
    metrics = calculate_metrics(quality, links)
    failed_metrics = {
        name: {"actual": metrics[name], "required": contract["thresholds"][name]}
        for name in METRIC_NAMES
        if metrics[name] < contract["thresholds"][name]
    }
    distributions = run_query(DISTRIBUTION_SQL)
    stratified_review = run_query(
        STRATIFIED_REVIEW_SQL,
        [contract["review_seed"], contract["review_sample_per_stratum"]],
    )
    anomaly_review = run_query(
        ANOMALY_REVIEW_SQL,
        [
            version,
            pattern,
            contract["review_seed"],
            contract["max_anomaly_review_items"],
        ],
    )
    generated_at = generated_at or datetime.now(timezone.utc)
    contract_bytes = json.dumps(
        contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    review_queue_counts = {
        "outdated_extraction": int(quality["outdated_extraction_rows"]),
        "nonpositive_amount": int(quality["nonpositive_amount_rows"]),
        "outcome_alignment": int(quality["outcome_alignment_issue_rows"]),
        "self_prior_reference": int(quality["self_prior_reference_rows"]),
        "non_simple_article_reference": int(quality["non_simple_article_rows"]),
        "unclear_outcome": int(quality["unclear_outcome_rows"]),
        "duplicate_identity_groups": int(quality["duplicate_identity_groups"]),
        "missing_decision_number": int(quality["missing_decision_number_rows"]),
        "missing_decision_date": int(quality["missing_decision_date_rows"]),
    }
    return {
        "schema_version": 1,
        "contract_version": contract["contract_version"],
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "generated_at_utc": generated_at.astimezone(timezone.utc).isoformat(),
        "deployed_commit": deployed_commit,
        "backend": {
            "mode": backend.get("mode"),
            "driver": backend.get("driver"),
            "connectable": backend.get("connectable"),
        },
        "execution_profile": contract["execution_profile"],
        "corpus": {
            "eligible_documents": int(quality["eligible_documents"]),
            "facts_total": int(quality["facts_total"]),
            "latest_fact_created_at": quality["latest_fact_created_at"],
        },
        "counts": {**quality, **links},
        "metrics": metrics,
        "failed_metrics": failed_metrics,
        "review_queue_counts": review_queue_counts,
        "distributions": distributions,
        "review_manifest": {
            "stratified": stratified_review,
            "anomalies": anomaly_review,
        },
    }


def baseline_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {key: report[key] for key in BASELINE_FIELDS}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_safe) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-output", type=Path)
    args = parser.parse_args()

    contract = load_contract(args.contract)
    if not args.execute:
        print(
            "DECISION_FACTS_QUALITY_PLAN="
            + json.dumps(
                {
                    "contract_version": contract["contract_version"],
                    "expected_extraction_version": contract["expected_extraction_version"],
                    "llm_calls_allowed": False,
                    "postgresql_writes_allowed": False,
                    "status": "dry_run",
                },
                sort_keys=True,
            )
        )
        return 0

    report = evaluate(contract, deployed_commit=args.commit)
    if args.output:
        _write_json(args.output, report)
        print(f"Saved operational decision-facts report: {args.output}")
    if args.baseline_output:
        _write_json(args.baseline_output, baseline_summary(report))
        print(f"Saved aggregate decision-facts baseline: {args.baseline_output}")
    print(
        "DECISION_FACTS_QUALITY_EVAL="
        + json.dumps(
            {
                "contract_version": report["contract_version"],
                "deployed_commit": report["deployed_commit"],
                "corpus": report["corpus"],
                "metrics": report["metrics"],
                "failed_metrics": report["failed_metrics"],
                "review_queue_counts": report["review_queue_counts"],
            },
            sort_keys=True,
        )
    )
    return 1 if report["failed_metrics"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
