#!/usr/bin/env python
"""Verify duplicate candidates against the official InfoHub public API.

The input is a protected full expert-review bundle. Dry-run is the default and
performs no network calls. Execute requires the exact input SHA-256 and exact
selected group/member counts printed by dry-run. It fetches only fixed
``infohub.rs.ge`` document UUIDs from the fixed ``infohubapi.rs.ge`` API,
stores hashes/metadata rather than legal text, and never connects to a database
or LLM. Technical equality is evidence for expert triage, not a legal verdict.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import stat
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from itertools import combinations
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT_PATH = (
    BACKEND_ROOT / "evaluation" / "infohub_duplicate_verification_contract.json"
)

TRIAGE_FIELDS = (
    "group_id",
    "candidate_class",
    "technical_assessment",
    "technical_confidence",
    "expert_action",
    "member_count",
    "fetch_success_count",
    "same_live_normalized_body",
    "same_live_identity",
    "minimum_live_similarity",
    "same_stored_file_hash",
    "same_stored_content",
    "same_stored_normalized_content",
    "technical_canonical_document_id",
    "technical_exclusion_candidates_json",
    "metadata_differences_json",
    "source_urls_json",
    "evidence_summary",
)

IDENTITY_FIELDS = ("name", "documentNumber", "type", "baseType")
COMPARISON_METADATA_FIELDS = (
    "receiptDate",
    "publishDate",
    "effectiveDate",
    "expirationDate",
    "createDate",
    "updateDate",
    "status",
    "parentDocumentId",
)


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_text(value: str) -> str:
    return _sha256(value.encode("utf-8"))


def _read_restricted(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError("input must be an existing regular file, not a symlink")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(
                f"input permissions must be 0600-compatible, got {mode:04o}"
            )
    return path.read_bytes()


def load_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != 1 or not contract.get("contract_version"):
        raise ValueError("unsupported InfoHub duplicate-verification contract")
    profile = contract.get("execution_profile") or {}
    required_false = (
        "llm_calls_allowed",
        "postgresql_reads_allowed",
        "postgresql_writes_allowed",
        "legal_verdicts_allowed",
        "automatic_exclusions_allowed",
    )
    if any(profile.get(field) is not False for field in required_false):
        raise ValueError("duplicate verifier execution profile is unsafe")
    if profile.get("full_report_must_remain_operational") is not True:
        raise ValueError("full duplicate-verification report must remain operational")
    if contract.get("allowed_source_host") != "infohub.rs.ge":
        raise ValueError("unexpected source host")
    if contract.get("official_api_base") != "https://infohubapi.rs.ge/api":
        raise ValueError("unexpected official API base")
    if set(contract.get("allowed_languages") or []) != {"ka", "ru", "en"}:
        raise ValueError("allowed languages are incomplete")
    threshold = float(contract.get("near_identity_threshold") or 0)
    if not 0.9 <= threshold < 1:
        raise ValueError("near-identity threshold is unsafe")
    return contract


def load_bundle(path: Path) -> tuple[dict[str, Any], str]:
    raw = _read_restricted(path)
    bundle = json.loads(raw.decode("utf-8"))
    if bundle.get("schema_version") != 1:
        raise ValueError("unsupported expert-review bundle schema")
    if bundle.get("bundle_type") != "decision_facts_full_expert_review":
        raise ValueError("input is not a full expert-review bundle")
    if bundle.get("review_contract", {}).get("database_writes_allowed") is not False:
        raise ValueError("input bundle does not prohibit database writes")
    groups = bundle.get("duplicate_groups")
    if not isinstance(groups, list):
        raise ValueError("duplicate groups are missing")
    group_ids: set[str] = set()
    member_total = 0
    for group in groups:
        group_id = str(group.get("group_id") or "")
        if not group_id or group_id in group_ids:
            raise ValueError("duplicate group identities are invalid")
        group_ids.add(group_id)
        members = group.get("members") or []
        if len(members) != int(group.get("member_count") or -1):
            raise ValueError(f"duplicate group member count mismatch: {group_id}")
        member_total += len(members)
    expected_counts = bundle.get("counts") or {}
    if expected_counts.get("duplicate_groups") != len(groups):
        raise ValueError("bundle duplicate-group count is invalid")
    if expected_counts.get("duplicate_members") != member_total:
        raise ValueError("bundle duplicate-member count is invalid")
    return bundle, _sha256(raw)


def select_groups(
    bundle: dict[str, Any],
    *,
    candidate_classes: set[str] | None = None,
    group_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    groups = list(bundle["duplicate_groups"])
    known_ids = {str(group["group_id"]) for group in groups}
    unknown_ids = sorted((group_ids or set()) - known_ids)
    if unknown_ids:
        raise ValueError(f"unknown requested group IDs: {unknown_ids}")
    if candidate_classes:
        groups = [
            group
            for group in groups
            if str(group.get("candidate_class")) in candidate_classes
        ]
    if group_ids:
        groups = [group for group in groups if str(group["group_id"]) in group_ids]
    return sorted(groups, key=lambda group: str(group["group_id"]))


def parse_source_url(source_url: str, contract: dict[str, Any]) -> tuple[str, str, str]:
    parsed = urlsplit(str(source_url or ""))
    if parsed.scheme != "https" or parsed.hostname != contract["allowed_source_host"]:
        raise ValueError("source URL is not on the allowed HTTPS InfoHub host")
    if parsed.port is not None or parsed.username or parsed.password:
        raise ValueError("source URL authority is invalid")
    if parsed.query or parsed.fragment:
        raise ValueError("source URL query/fragment is not allowed")
    match = re.fullmatch(
        r"/(ka|ru|en)/workspace/document/([0-9a-fA-F-]{36})/?", parsed.path
    )
    if not match or match.group(1) not in set(contract["allowed_languages"]):
        raise ValueError("source URL path is not an InfoHub document UUID")
    language, raw_key = match.groups()
    try:
        key = str(uuid.UUID(raw_key))
    except ValueError as exc:
        raise ValueError("source URL document key is not a UUID") from exc
    api_url = (
        f"{contract['official_api_base']}/documents/{key}/details-by-key"
        "?openFromSearch=false"
    )
    return language, key, api_url


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self.suppressed_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "noscript"}:
            self.suppressed_depth = max(0, self.suppressed_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self.suppressed_depth and data:
            self.parts.append(data)


def html_to_text(value: Any) -> str:
    parser = _VisibleTextParser()
    parser.feed(str(value or ""))
    parser.close()
    return "\n".join(part.strip() for part in parser.parts if part.strip())


def normalize_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\u00a0", " ")
    # NFC preserves legally meaningful compatibility characters such as
    # Georgian superscript article numbering (98² must not become 982).
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.casefold().split())


def _nested_name(value: Any) -> str | None:
    if isinstance(value, dict):
        name = str(value.get("name") or "").strip()
        return name or None
    text = str(value or "").strip()
    return text or None


def _stable_metadata_value(value: Any) -> Any:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, (dict, list)):
        return json.loads(_canonical_json(value).decode("utf-8"))
    return value


def summarize_api_payload(
    payload: dict[str, Any], *, source_url: str, language: str, key: str, api_url: str
) -> dict[str, Any]:
    response_key = str(payload.get("uniqueKey") or "")
    if response_key.casefold() != key.casefold():
        raise ValueError("official API returned a different document key")
    body = html_to_text(
        payload.get("description") or payload.get("additionalDescription") or ""
    )
    normalized_body = normalize_text(body)
    name = str(payload.get("name") or "").strip()
    type_name = _nested_name(payload.get("type"))
    base_type_name = _nested_name(payload.get("baseType"))
    canonical_text = "\n\n".join(
        value for value in (name, type_name, base_type_name, body) if value
    )
    normalized_canonical = normalize_text(canonical_text)
    decision_content = _stable_metadata_value(payload.get("documentDecisionContent"))
    result = {
        "ok": True,
        "source_url": source_url,
        "official_api_url": api_url,
        "language": language,
        "unique_key": key,
        "metadata": {
            "name": name or None,
            "documentNumber": str(payload.get("documentNumber") or "").strip() or None,
            "type": type_name,
            "baseType": base_type_name,
            "status": _nested_name(payload.get("status")),
            "receiptDate": payload.get("receiptDate"),
            "publishDate": payload.get("publishDate"),
            "effectiveDate": payload.get("effectiveDate"),
            "expirationDate": payload.get("expirationDate"),
            "createDate": payload.get("createDate"),
            "updateDate": payload.get("updateDate"),
            "parentDocumentId": payload.get("parentDocumentId"),
        },
        "body_length": len(body),
        "normalized_body_length": len(normalized_body),
        "normalized_body_sha256": _hash_text(normalized_body),
        "normalized_canonical_length": len(normalized_canonical),
        "normalized_canonical_sha256": _hash_text(normalized_canonical),
        "decision_content_sha256": (
            _sha256(_canonical_json(decision_content))
            if decision_content is not None
            else None
        ),
        "_normalized_body": normalized_body,
    }
    return result


class RateLimiter:
    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.interval_seconds
        if delay:
            time.sleep(delay)


def fetch_official_detail(
    source_url: str,
    contract: dict[str, Any],
    *,
    timeout_seconds: float,
    retries: int,
    limiter: RateLimiter,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    try:
        language, key, api_url = parse_source_url(source_url, contract)
    except ValueError as exc:
        return {"ok": False, "source_url": source_url, "error": str(exc)}
    headers = {
        "User-Agent": "InfoHubAI-DuplicateVerifier/1.0",
        "Accept": "application/json, text/plain, */*",
        "languagecode": language,
        "Referer": "https://infohub.rs.ge/",
        "Origin": "https://infohub.rs.ge",
    }
    maximum_bytes = int(contract["maximum_response_bytes"])
    last_error = "unknown fetch error"
    for attempt in range(retries + 1):
        limiter.wait()
        request = urllib.request.Request(api_url, headers=headers)
        try:
            with opener(request, timeout=timeout_seconds) as response:
                raw = response.read(maximum_bytes + 1)
            if len(raw) > maximum_bytes:
                raise ValueError("official API response exceeds the size limit")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("official API response is not an object")
            return summarize_api_payload(
                payload,
                source_url=source_url,
                language=language,
                key=key,
                api_url=api_url,
            )
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(min(2**attempt, 4))
    return {
        "ok": False,
        "source_url": source_url,
        "official_api_url": api_url,
        "language": language,
        "unique_key": key,
        "error": last_error,
    }


def _all_same_nonempty(values: list[Any]) -> bool:
    normalized = [str(value) for value in values if value not in (None, "")]
    return len(normalized) == len(values) and len(set(normalized)) == 1


def _word_shingles(value: str, size: int = 5) -> set[tuple[str, ...]]:
    words = value.split()
    if not words:
        return set()
    if len(words) < size:
        return {tuple(words)}
    return {
        tuple(words[index : index + size]) for index in range(len(words) - size + 1)
    }


def text_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    left_shingles = _word_shingles(left)
    right_shingles = _word_shingles(right)
    if not left_shingles or not right_shingles:
        return 0.0
    return round(
        len(left_shingles & right_shingles) / len(left_shingles | right_shingles),
        6,
    )


def _different_metadata_fields(results: list[dict[str, Any]]) -> list[str]:
    different = []
    for field in COMPARISON_METADATA_FIELDS:
        values = [
            _canonical_json(result.get("metadata", {}).get(field)).decode("utf-8")
            for result in results
        ]
        if len(set(values)) > 1:
            different.append(field)
    return different


def compare_group(
    group: dict[str, Any],
    fetched_by_url: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    members = group["members"]
    live_results = [
        fetched_by_url[str(member.get("source_url") or "")] for member in members
    ]
    successful = [result for result in live_results if result.get("ok")]
    all_fetched = len(successful) == len(members)
    body_hashes = [result.get("normalized_body_sha256") for result in successful]
    same_live_body = all_fetched and _all_same_nonempty(body_hashes)
    same_live_identity = all_fetched and all(
        _all_same_nonempty(
            [result.get("metadata", {}).get(field) for result in successful]
        )
        for field in IDENTITY_FIELDS
    )
    similarities = [
        text_similarity(left["_normalized_body"], right["_normalized_body"])
        for left, right in combinations(successful, 2)
    ]
    minimum_similarity = (
        min(similarities) if similarities else (1.0 if all_fetched else 0.0)
    )
    metadata_differences = _different_metadata_fields(successful) if all_fetched else []
    stored_file_hashes = [member.get("file_hash") for member in members]
    stored_content_hashes = [member.get("content_md5") for member in members]
    stored_normalized_hashes = [
        member.get("normalized_content_md5") for member in members
    ]
    same_stored_file_hash = _all_same_nonempty(stored_file_hashes)
    same_stored_content = _all_same_nonempty(stored_content_hashes)
    same_stored_normalized = _all_same_nonempty(stored_normalized_hashes)
    near_threshold = float(contract["near_identity_threshold"])

    if not all_fetched:
        assessment = "verification_incomplete"
        confidence = "none"
        expert_action = "retry_or_manual_review"
    elif same_live_body and same_live_identity:
        assessment = "official_content_identical"
        confidence = "high"
        expert_action = "expert_batch_confirmation_candidate"
    elif same_live_body:
        assessment = "same_content_identity_mismatch"
        confidence = "medium"
        expert_action = "manual_review"
    elif minimum_similarity >= near_threshold and same_live_identity:
        assessment = "official_content_near_identical"
        confidence = "medium"
        expert_action = "manual_review"
    else:
        assessment = "official_content_differs"
        confidence = "none"
        expert_action = "manual_review"

    canonical = None
    exclusions: list[str] = []
    if assessment == "official_content_identical":
        document_ids = sorted(str(member["document_id"]) for member in members)
        canonical = document_ids[0]
        exclusions = document_ids[1:]

    if all_fetched:
        evidence_summary = (
            f"Official API returned {len(successful)}/{len(members)} records; "
            f"assessment={assessment}; minimum normalized-body similarity="
            f"{minimum_similarity:.6f}; identity fields "
            f"{'match' if same_live_identity else 'differ'}; metadata differences="
            f"{','.join(metadata_differences) if metadata_differences else 'none'}. "
            "No legal verdict or exclusion was applied."
        )
    else:
        evidence_summary = (
            f"Official API returned {len(successful)}/{len(members)} records; "
            "verification is incomplete and no legal verdict or exclusion was applied."
        )

    public_results = []
    for member, result in zip(members, live_results):
        public_result = {
            key: value for key, value in result.items() if not key.startswith("_")
        }
        public_results.append(
            {
                "document_id": str(member["document_id"]),
                "facts_id": str(member["facts_id"]),
                "stored": {
                    "file_hash": member.get("file_hash"),
                    "content_length": member.get("content_length"),
                    "content_md5": member.get("content_md5"),
                    "normalized_content_md5": member.get("normalized_content_md5"),
                    "decision_number": member.get("decision_number"),
                    "decision_date": member.get("decision_date"),
                },
                "official_api": public_result,
            }
        )

    return {
        "group_id": group["group_id"],
        "candidate_class": group["candidate_class"],
        "technical_assessment": assessment,
        "technical_confidence": confidence,
        "expert_action": expert_action,
        "member_count": len(members),
        "fetch_success_count": len(successful),
        "same_live_normalized_body": same_live_body,
        "same_live_identity": same_live_identity,
        "minimum_live_similarity": minimum_similarity,
        "same_stored_file_hash": same_stored_file_hash,
        "same_stored_content": same_stored_content,
        "same_stored_normalized_content": same_stored_normalized,
        "technical_canonical_document_id": canonical,
        "technical_exclusion_candidates": exclusions,
        "metadata_differences": metadata_differences,
        "source_urls": [str(member.get("source_url") or "") for member in members],
        "evidence_summary": evidence_summary,
        "members": public_results,
    }


def verify_groups(
    groups: list[dict[str, Any]],
    contract: dict[str, Any],
    *,
    timeout_seconds: float,
    retries: int,
    max_workers: int,
    request_interval_seconds: float,
    fetcher: Callable[..., dict[str, Any]] = fetch_official_detail,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_urls = sorted(
        {
            str(member.get("source_url") or "")
            for group in groups
            for member in group["members"]
        }
    )
    limiter = RateLimiter(request_interval_seconds)
    fetched_by_url: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                fetcher,
                source_url,
                contract,
                timeout_seconds=timeout_seconds,
                retries=retries,
                limiter=limiter,
            ): source_url
            for source_url in source_urls
        }
        for future in as_completed(futures):
            source_url = futures[future]
            try:
                fetched_by_url[source_url] = future.result()
            except Exception as exc:  # pragma: no cover - defensive worker boundary
                fetched_by_url[source_url] = {
                    "ok": False,
                    "source_url": source_url,
                    "error": f"{type(exc).__name__}: {exc}",
                }
    comparisons = [compare_group(group, fetched_by_url, contract) for group in groups]
    assessment_counts: dict[str, int] = {}
    for comparison in comparisons:
        key = comparison["technical_assessment"]
        assessment_counts[key] = assessment_counts.get(key, 0) + 1
    fetch_successes = sum(
        result.get("ok") is True for result in fetched_by_url.values()
    )
    summary = {
        "groups": len(groups),
        "members": sum(len(group["members"]) for group in groups),
        "official_api_requests": len(source_urls),
        "fetch_successes": fetch_successes,
        "fetch_failures": len(source_urls) - fetch_successes,
        "assessment_counts": dict(sorted(assessment_counts.items())),
    }
    return comparisons, summary


def build_report(
    *,
    bundle: dict[str, Any],
    bundle_sha256: str,
    contract: dict[str, Any],
    selected_groups: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    verification_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_type": "infohub_duplicate_technical_verification",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract_version": contract["contract_version"],
        "contract_sha256": _sha256(_canonical_json(contract)),
        "execution_profile": contract["execution_profile"],
        "source": {
            "bundle_sha256": bundle_sha256,
            "source_snapshot_sha256": bundle["source"]["source_snapshot_sha256"],
            "deployed_commit": bundle["source"].get("deployed_commit"),
            "selected_group_ids_sha256": _sha256(
                _canonical_json([group["group_id"] for group in selected_groups])
            ),
        },
        "summary": verification_summary,
        "groups": comparisons,
        "legal_effect": {
            "legal_verdicts_created": False,
            "database_changes_created": False,
            "automatic_exclusions_created": False,
            "expert_confirmation_required": True,
        },
    }


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def render_triage_csv(report: dict[str, Any]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=TRIAGE_FIELDS, extrasaction="raise")
    writer.writeheader()
    for group in report["groups"]:
        row = {
            **{field: group.get(field) for field in TRIAGE_FIELDS},
            "technical_exclusion_candidates_json": group.get(
                "technical_exclusion_candidates"
            ),
            "metadata_differences_json": group.get("metadata_differences"),
            "source_urls_json": group.get("source_urls"),
        }
        writer.writerow({field: _csv_safe(row.get(field)) for field in TRIAGE_FIELDS})
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def render_instructions(report: dict[str, Any]) -> bytes:
    summary = report["summary"]
    text = f"""# InfoHub duplicate technical verification

Scope: {summary['groups']} groups / {summary['members']} members.
Official API fetches: {summary['fetch_successes']} succeeded and
{summary['fetch_failures']} failed.

`official_content_identical` means the current official API returned matching
normalized visible bodies and identity fields. It is strong technical evidence,
not a legal verdict. Review metadata differences and sample the official URLs
before recording `true_duplicate` in the separate expert worksheet.

`official_content_near_identical`, `same_content_identity_mismatch`,
`official_content_differs` and `verification_incomplete` always require manual
review or a retry. Never paste technical assessment columns into immutable
expert-workbook columns. This report cannot update PostgreSQL, create a legal
verdict or exclude a document.
"""
    return text.encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    os.chmod(path, 0o600)


def materialize(output_dir: Path, report: dict[str, Any]) -> dict[str, str]:
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("output directory already exists; refusing overwrite")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(mode=0o700)
    os.chmod(output_dir, 0o700)
    payloads = {
        "technical_verification.json": json.dumps(
            report, ensure_ascii=False, indent=2
        ).encode("utf-8")
        + b"\n",
        "duplicate_technical_triage.csv": render_triage_csv(report),
        "README.md": render_instructions(report),
    }
    hashes = {}
    for name, payload in payloads.items():
        _write_exclusive(output_dir / name, payload)
        hashes[name] = _sha256(payload)
    checksums = "".join(
        f"{digest}  {name}\n" for name, digest in sorted(hashes.items())
    )
    _write_exclusive(output_dir / "SHA256SUMS", checksums.encode("ascii"))
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument(
        "--candidate-class",
        action="append",
        choices=["exact", "likely", "ambiguous"],
        dest="candidate_classes",
    )
    parser.add_argument("--group-id", action="append", dest="group_ids")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--expected-groups", type=int)
    parser.add_argument("--expected-members", type=int)
    parser.add_argument("--max-workers", type=int)
    parser.add_argument("--request-interval-seconds", type=float)
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--retries", type=int)
    args = parser.parse_args()

    contract = load_contract(args.contract)
    bundle, bundle_sha256 = load_bundle(args.bundle)
    classes = set(args.candidate_classes or []) or None
    group_ids = set(args.group_ids or []) or None
    groups = select_groups(bundle, candidate_classes=classes, group_ids=group_ids)
    member_count = sum(len(group["members"]) for group in groups)
    plan = {
        "contract_version": contract["contract_version"],
        "input_sha256": bundle_sha256,
        "groups": len(groups),
        "members": member_count,
        "official_api_requests": len(
            {
                str(member.get("source_url") or "")
                for group in groups
                for member in group["members"]
            }
        ),
        "candidate_class_counts": {
            candidate_class: sum(
                group.get("candidate_class") == candidate_class for group in groups
            )
            for candidate_class in ("exact", "likely", "ambiguous")
        },
    }
    prefix = "INFOHUB_DUPLICATE_VERIFICATION"
    if not args.execute:
        print(prefix + "_PLAN=" + json.dumps(plan, sort_keys=True))
        return 0

    if not groups:
        parser.error("selected duplicate-verification scope is empty")
    if args.output_dir is None:
        parser.error("--output-dir is required with --execute")
    if not args.expected_input_sha256:
        parser.error("--expected-input-sha256 is required with --execute")
    if args.expected_input_sha256.lower() != bundle_sha256:
        raise ValueError("expert-review bundle changed after dry run")
    checks = (
        (args.expected_groups, len(groups), "selected groups"),
        (args.expected_members, member_count, "selected members"),
    )
    for expected, actual, label in checks:
        if expected is None or expected != actual:
            raise ValueError(f"{label} changed: expected {expected}, got {actual}")

    max_workers = args.max_workers or int(contract["default_max_workers"])
    maximum_workers = int(contract["maximum_max_workers"])
    if not 1 <= max_workers <= maximum_workers:
        parser.error(f"--max-workers must be between 1 and {maximum_workers}")
    interval = (
        float(args.request_interval_seconds)
        if args.request_interval_seconds is not None
        else float(contract["default_request_interval_seconds"])
    )
    timeout = (
        float(args.timeout_seconds)
        if args.timeout_seconds is not None
        else float(contract["default_timeout_seconds"])
    )
    retries = (
        int(args.retries)
        if args.retries is not None
        else int(contract["default_retries"])
    )
    if interval < 0 or not 1 <= timeout <= 120 or not 0 <= retries <= 5:
        parser.error("network bounds are invalid")

    comparisons, verification_summary = verify_groups(
        groups,
        contract,
        timeout_seconds=timeout,
        retries=retries,
        max_workers=max_workers,
        request_interval_seconds=interval,
    )
    report = build_report(
        bundle=bundle,
        bundle_sha256=bundle_sha256,
        contract=contract,
        selected_groups=groups,
        comparisons=comparisons,
        verification_summary=verification_summary,
    )
    hashes = materialize(args.output_dir, report)
    output = {
        **plan,
        **verification_summary,
        "output_dir": str(args.output_dir),
        "files": hashes,
    }
    print(prefix + "=" + json.dumps(output, sort_keys=True))
    return 1 if verification_summary["fetch_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
