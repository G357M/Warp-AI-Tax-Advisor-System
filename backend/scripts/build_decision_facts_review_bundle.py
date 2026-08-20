#!/usr/bin/env python
"""Build a restricted, deterministic legal-expert review bundle.

The input is the operational report produced by
``evaluate_decision_facts_quality.py``. This tool never connects to the
database or an LLM. Dry-run is the default; materialization requires the exact
expected number of unique review items.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXTRACTION_FIELDS = (
    "authority_body",
    "dispute_type",
    "outcome",
    "in_favor",
    "decision_number",
    "decision_date",
    "contested_articles",
    "has_amount",
)

VERIFICATION_FIELDS = (
    "source_accessible",
    "identity_correct",
    "authority_body_correct",
    "dispute_type_correct",
    "outcome_correct",
    "in_favor_correct",
    "decision_number_correct",
    "decision_date_correct",
    "contested_articles_correct",
    "amount_presence_correct",
)

CSV_FIELDS = (
    "review_id",
    "sample_reasons",
    "document_id",
    "title",
    "source_url",
    *EXTRACTION_FIELDS,
    "review_state",
    *VERIFICATION_FIELDS,
    "reviewer",
    "reviewed_at_utc",
    "notes",
)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_restricted_report(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("input must be an existing regular file, not a symlink")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"operational report permissions must be 0600-compatible, got {mode:04o}"
            )
    raw = path.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    if report.get("schema_version") != 1:
        raise ValueError("unsupported decision-facts report schema_version")
    if not report.get("contract_version") or not report.get("contract_sha256"):
        raise ValueError("report contract identity is missing")
    profile = report.get("execution_profile") or {}
    if profile.get("llm_calls_allowed") is not False:
        raise ValueError("review source must prohibit LLM calls")
    if profile.get("postgresql_writes_allowed") is not False:
        raise ValueError("review source must prohibit PostgreSQL writes")
    manifest = report.get("review_manifest") or {}
    if not isinstance(manifest.get("stratified"), list):
        raise ValueError("stratified review manifest is missing")
    if not isinstance(manifest.get("anomalies"), list):
        raise ValueError("anomaly review manifest is missing")
    return report, _sha256_bytes(raw)


def _review_id(contract_version: str, document_id: str) -> str:
    digest = hashlib.sha256(
        f"{contract_version}|{document_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"DFR-{digest.upper()}"


def build_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Deduplicate review rows and retain every sampling reason."""

    contract_version = str(report["contract_version"])
    merged: dict[str, dict[str, Any]] = {}

    def add_row(row: dict[str, Any], reasons: list[str]) -> None:
        document_id = str(row.get("document_id") or "").strip()
        if not document_id:
            raise ValueError("review row is missing document_id")
        item = merged.setdefault(
            document_id,
            {
                "review_id": _review_id(contract_version, document_id),
                "sample_reasons": set(),
                "document_id": document_id,
                "title": row.get("title"),
                "source_url": row.get("source_url"),
                "extraction": {field: row.get(field) for field in EXTRACTION_FIELDS},
                "review": {
                    "review_state": "pending",
                    **{field: None for field in VERIFICATION_FIELDS},
                    "reviewer": None,
                    "reviewed_at_utc": None,
                    "notes": "",
                },
            },
        )
        item["sample_reasons"].update(reasons)
        for field in ("title", "source_url"):
            if item.get(field) is None and row.get(field) is not None:
                item[field] = row[field]
        for field in EXTRACTION_FIELDS:
            if item["extraction"].get(field) is None and row.get(field) is not None:
                item["extraction"][field] = row[field]

    manifest = report["review_manifest"]
    for row in manifest["stratified"]:
        add_row(
            row,
            [f"stratum:{row.get('authority_body')}:{row.get('outcome')}"],
        )
    for row in manifest["anomalies"]:
        flags = row.get("anomaly_flags") or []
        if not isinstance(flags, list) or not flags:
            raise ValueError("anomaly review row is missing anomaly_flags")
        add_row(row, [f"anomaly:{flag}" for flag in flags])

    items = []
    for item in merged.values():
        item["sample_reasons"] = sorted(item["sample_reasons"])
        items.append(item)
    return sorted(items, key=lambda item: item["review_id"])


def build_bundle(
    report: dict[str, Any], report_sha256: str, *, generated_at: datetime | None = None
) -> dict[str, Any]:
    items = build_items(report)
    generated_at = generated_at or datetime.now(timezone.utc)
    reason_counts: dict[str, int] = {}
    for item in items:
        for reason in item["sample_reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "schema_version": 1,
        "bundle_type": "decision_facts_expert_review",
        "generated_at_utc": generated_at.astimezone(timezone.utc).isoformat(),
        "source": {
            "report_sha256": report_sha256,
            "contract_version": report["contract_version"],
            "contract_sha256": report["contract_sha256"],
            "deployed_commit": report.get("deployed_commit"),
            "report_generated_at_utc": report.get("generated_at_utc"),
        },
        "review_contract": {
            "allowed_verdicts": [
                "correct",
                "incorrect",
                "not_applicable",
                "unable_to_verify",
            ],
            "completion_rule": (
                "Set review_state=complete only after checking the official source; "
                "this bundle does not itself constitute legal verification."
            ),
        },
        "counts": {
            "unique_items": len(items),
            "reason_counts": dict(sorted(reason_counts.items())),
        },
        "items": items,
    }


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def render_csv(bundle: dict[str, Any]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise")
    writer.writeheader()
    for item in bundle["items"]:
        extraction = item["extraction"]
        review = item["review"]
        row = {
            "review_id": item["review_id"],
            "sample_reasons": " | ".join(item["sample_reasons"]),
            "document_id": item["document_id"],
            "title": item.get("title"),
            "source_url": item.get("source_url"),
            **extraction,
            **review,
        }
        writer.writerow({key: _csv_safe(value) for key, value in row.items()})
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def render_instructions(bundle: dict[str, Any]) -> bytes:
    text = f"""# Decision-facts expert review

This restricted bundle contains {bundle['counts']['unique_items']} deterministic review items.

1. Open the official `source_url`; never judge only from the extracted fields.
2. Use only: `correct`, `incorrect`, `not_applicable`, `unable_to_verify`.
3. Fill reviewer and UTC review time, add a concise note for every incorrect field.
4. Set `review_state` to `complete` only when the item has been checked against the source.
5. Keep the bundle restricted: it is an operational review artifact, not a Git fixture.

Passing automated metrics and an empty review sheet are not legal verification.
"""
    return text.encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def materialize_bundle(output_dir: Path, bundle: dict[str, Any]) -> dict[str, str]:
    if output_dir.exists():
        raise FileExistsError("output directory already exists; refusing to overwrite it")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(mode=0o700)
    os.chmod(output_dir, 0o700)

    payloads = {
        "review_bundle.json": json.dumps(
            bundle, ensure_ascii=False, indent=2
        ).encode("utf-8")
        + b"\n",
        "review_sheet.csv": render_csv(bundle),
        "REVIEW_INSTRUCTIONS.md": render_instructions(bundle),
    }
    hashes: dict[str, str] = {}
    for name, payload in payloads.items():
        _write_exclusive(output_dir / name, payload)
        hashes[name] = _sha256_bytes(payload)
    checksums = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    _write_exclusive(output_dir / "SHA256SUMS", checksums.encode("ascii"))
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-items", type=int)
    parser.add_argument("--expected-report-sha256")
    args = parser.parse_args()

    report, report_sha256 = _read_restricted_report(args.input)
    bundle = build_bundle(report, report_sha256)
    summary = {
        "contract_version": bundle["source"]["contract_version"],
        "deployed_commit": bundle["source"]["deployed_commit"],
        "report_sha256": report_sha256,
        "unique_items": bundle["counts"]["unique_items"],
        "reason_counts": bundle["counts"]["reason_counts"],
    }

    if not args.execute:
        print("DECISION_FACTS_REVIEW_PLAN=" + json.dumps(summary, sort_keys=True))
        return 0
    if args.output_dir is None:
        parser.error("--output-dir is required with --execute")
    if args.expected_items is None or args.expected_items < 1:
        parser.error("a positive --expected-items is required with --execute")
    if not args.expected_report_sha256:
        parser.error("--expected-report-sha256 is required with --execute")
    if args.expected_report_sha256.lower() != report_sha256:
        raise ValueError(
            "operational report changed after review plan: "
            f"expected {args.expected_report_sha256.lower()}, got {report_sha256}"
        )
    if args.expected_items != bundle["counts"]["unique_items"]:
        raise ValueError(
            "review item count changed: "
            f"expected {args.expected_items}, got {bundle['counts']['unique_items']}"
        )

    hashes = materialize_bundle(args.output_dir, bundle)
    summary["output_dir"] = str(args.output_dir)
    summary["files"] = dict(sorted(hashes.items()))
    print("DECISION_FACTS_REVIEW_BUNDLE=" + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
