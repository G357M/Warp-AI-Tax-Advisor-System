#!/usr/bin/env python3
"""Audit Matsne same-origin browser capture receipts without writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from legal_temporal.browser_capture_receipts import (
    AUDITOR_IMPLEMENTATION,
    audit_browser_capture_receipts,
    browser_receipt_file,
    compact_browser_receipt_audit,
)
from legal_temporal.publication_capture import read_capture_plan
from legal_temporal.publication_editions import (
    PublicationEditionValidationError,
    _load_json_bytes,
    _read_bounded,
)


CHECKPOINT_CONTRACT = "matsne-browser-capture-receipt-audit-checkpoint-v1"
MAX_CHECKPOINT_BYTES = 4 * 1024 * 1024
CHECKPOINT_FIELDS = frozenset(
    {
        "contract",
        "auditor_implementation",
        "plan_sha256",
        "plan_file_sha256",
        "details",
        "database_writes_allowed",
        "public_answer_routing_changed",
    }
)
DETAIL_FIELDS = frozenset(
    {
        "publication",
        "ready",
        "receipt_file",
        "receipt_sha256",
        "page_sha256",
        "tree_sha256",
        "article_count",
        "errors",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="optional resumable progress file; must be outside the evidence bundle",
    )
    parser.add_argument(
        "--expected-checkpoint-sha256",
        help="required SHA-256 pin when resuming an existing checkpoint",
    )
    parser.add_argument("--progress-every", type=int, default=10)
    return parser.parse_args()


def _outside_bundle(path: Path, bundle: Path, *, label: str) -> None:
    try:
        path.resolve(strict=False).relative_to(bundle.resolve(strict=True))
    except ValueError:
        return
    except OSError as exc:
        raise PublicationEditionValidationError(
            f"cannot resolve {label} or evidence bundle"
        ) from exc
    raise PublicationEditionValidationError(
        f"{label} must be outside the immutable evidence bundle"
    )


def _validate_checkpoint_detail(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != DETAIL_FIELDS:
        raise PublicationEditionValidationError("checkpoint detail fields mismatch")
    publication = value["publication"]
    article_count = value["article_count"]
    if (
        isinstance(publication, bool)
        or not isinstance(publication, int)
        or publication < 0
        or value["ready"] is not True
        or value["receipt_file"] != browser_receipt_file(publication)
        or any(
            not isinstance(value[field], str)
            or not _SHA256_RE.fullmatch(value[field])
            for field in ("receipt_sha256", "page_sha256", "tree_sha256")
        )
        or isinstance(article_count, bool)
        or not isinstance(article_count, int)
        or article_count < 1
        or value["errors"] != []
    ):
        raise PublicationEditionValidationError("checkpoint detail is invalid")
    return value


def _read_checkpoint(
    path: Path,
    *,
    expected_sha256: str,
    plan_sha256: str,
    plan_file_sha256: str,
) -> dict[int, dict[str, object]]:
    if not _SHA256_RE.fullmatch(expected_sha256):
        raise PublicationEditionValidationError(
            "expected checkpoint SHA-256 must be lowercase hexadecimal"
        )
    raw = _read_bounded(path, MAX_CHECKPOINT_BYTES, label="audit checkpoint")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise PublicationEditionValidationError("audit checkpoint SHA-256 pin mismatch")
    checkpoint = _load_json_bytes(raw, label="audit checkpoint")
    if set(checkpoint) != CHECKPOINT_FIELDS:
        raise PublicationEditionValidationError("audit checkpoint fields mismatch")
    if (
        checkpoint["contract"] != CHECKPOINT_CONTRACT
        or checkpoint["auditor_implementation"] != AUDITOR_IMPLEMENTATION
        or checkpoint["plan_sha256"] != plan_sha256
        or checkpoint["plan_file_sha256"] != plan_file_sha256
        or checkpoint["database_writes_allowed"] is not False
        or checkpoint["public_answer_routing_changed"] is not False
        or not isinstance(checkpoint["details"], list)
    ):
        raise PublicationEditionValidationError(
            "audit checkpoint contract, implementation, plan, or safety flags mismatch"
        )
    details: dict[int, dict[str, object]] = {}
    for raw_detail in checkpoint["details"]:
        detail = _validate_checkpoint_detail(raw_detail)
        publication = detail["publication"]
        if publication in details:
            raise PublicationEditionValidationError(
                "audit checkpoint contains duplicate publications"
            )
        details[publication] = detail
    return details


def _write_checkpoint(
    path: Path,
    *,
    plan_sha256: str,
    plan_file_sha256: str,
    details: dict[int, dict[str, object]],
) -> str:
    checkpoint = {
        "contract": CHECKPOINT_CONTRACT,
        "auditor_implementation": AUDITOR_IMPLEMENTATION,
        "plan_sha256": plan_sha256,
        "plan_file_sha256": plan_file_sha256,
        "details": [details[key] for key in sorted(details)],
        "database_writes_allowed": False,
        "public_answer_routing_changed": False,
    }
    raw = (json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise PublicationEditionValidationError("audit checkpoint exceeds size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    args = parse_args()
    if not 1 <= args.progress_every <= 1_000:
        raise ValueError("--progress-every must be within 1..1000")
    if args.expected_checkpoint_sha256 and not args.checkpoint:
        raise ValueError("--expected-checkpoint-sha256 requires --checkpoint")

    plan, plan_file_sha256 = read_capture_plan(args.plan)
    if plan["plan_sha256"] != args.expected_plan_sha256:
        raise PublicationEditionValidationError("capture plan identity pin mismatch")

    checkpoint_details: dict[int, dict[str, object]] = {}
    latest_checkpoint_sha: str | None = None
    if args.checkpoint:
        _outside_bundle(args.checkpoint, args.bundle, label="audit checkpoint")
        if args.checkpoint.exists() or args.checkpoint.is_symlink():
            if not args.expected_checkpoint_sha256:
                raise ValueError(
                    "resuming an existing checkpoint requires "
                    "--expected-checkpoint-sha256"
                )
            checkpoint_details = _read_checkpoint(
                args.checkpoint,
                expected_sha256=args.expected_checkpoint_sha256,
                plan_sha256=plan["plan_sha256"],
                plan_file_sha256=plan_file_sha256,
            )
        elif args.expected_checkpoint_sha256:
            raise ValueError("expected checkpoint does not exist")

    def progress(completed: int, total: int, detail: dict[str, object]) -> None:
        nonlocal latest_checkpoint_sha
        publication = detail["publication"]
        if detail["ready"] is True:
            checkpoint_details[publication] = detail
        else:
            checkpoint_details.pop(publication, None)
        if args.checkpoint:
            latest_checkpoint_sha = _write_checkpoint(
                args.checkpoint,
                plan_sha256=plan["plan_sha256"],
                plan_file_sha256=plan_file_sha256,
                details=checkpoint_details,
            )
        if completed % args.progress_every == 0 or completed == total:
            checkpoint_text = (
                f" checkpoint_sha256={latest_checkpoint_sha}"
                if latest_checkpoint_sha
                else ""
            )
            print(
                "MATSNE_BROWSER_CAPTURE_RECEIPT_AUDIT_PROGRESS "
                f"completed={completed}/{total} publication={publication} "
                f"state={'ready' if detail['ready'] else 'pending'}"
                f"{checkpoint_text}",
                file=sys.stderr,
                flush=True,
            )

    try:
        report = audit_browser_capture_receipts(
            args.plan,
            args.bundle,
            expected_plan_sha256=args.expected_plan_sha256,
            resume_details=checkpoint_details,
            progress=progress,
        )
    except KeyboardInterrupt:
        checkpoint_text = (
            f" checkpoint_sha256={latest_checkpoint_sha}"
            if latest_checkpoint_sha
            else ""
        )
        print(
            "MATSNE_BROWSER_CAPTURE_RECEIPT_AUDIT_INTERRUPTED" + checkpoint_text,
            file=sys.stderr,
            flush=True,
        )
        return 130
    if args.report:
        if args.report.exists() or args.report.is_symlink():
            raise ValueError("audit report output already exists")
        with args.report.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        try:
            args.report.chmod(0o600)
        except OSError:
            pass
    print(
        "MATSNE_BROWSER_CAPTURE_RECEIPT_AUDIT="
        + json.dumps(compact_browser_receipt_audit(report), sort_keys=True)
    )
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
