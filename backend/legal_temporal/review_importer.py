"""PostgreSQL-only, bounded append-only admission of reviewed candidates.

Never creates operations, provision versions or publication events. Imported
expert_verified applies to an operation candidate, not authoritative legal text.
"""

from datetime import UTC, datetime
import hashlib
import json
import time
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text

from legal_temporal.backfill import (
    BACKFILL_CONTRACT, canonical_json_bytes, operation_key, parse_iso_date, parse_iso_datetime,
    parse_workspace_source_url, sha256_json, validate_official_api_bytes,
)
from legal_temporal.expert_review import ReviewValidationError
from legal_temporal.review_admission import (
    ADMISSION_CONTRACT, MAX_ADMISSIONS, validate_rollback_proof,
)
from legal_temporal.schema_contract import SCHEMA_CONTRACT_SHA256, SCHEMA_VERSION
from models.legal_temporal import (
    LegalAct, LegalActPublication, LegalAmendmentOperation, LegalProvision,
    LegalProvisionVersion, LegalReviewEvent, LegalSourceBlob, LegalSourceSnapshot, LegalSourceObservation,
)


def _equal(actual, expected, label):
    if actual != expected or type(actual) is not type(expected):
        raise ReviewValidationError(f"database lineage mismatch: {label}")


def _record(row):
    return json.loads(json.dumps({c.key: getattr(row, c.key) for c in row.__mapper__.column_attrs}, default=str))


def _scope(db, manifest, texts, plan, *, deadline=None):
    """Resolve by fingerprint, but prove every relationship and both raw anchors."""
    installed = db.execute(text(
        "SELECT contract_sha256 FROM legal_temporal_schema_migrations WHERE schema_version=:version"
    ), {"version": SCHEMA_VERSION}).scalar_one_or_none()
    _equal(installed, SCHEMA_CONTRACT_SHA256, "schema contract")
    source_by_id = {s["legacy_document_id"]: s for s in manifest["sources"]}
    candidates = {c["candidate_fingerprint"]: c for a in manifest["amendments"] for c in a["candidates"]}
    records, snapshots, entities, event_specs = {}, {}, set(), []

    def remember(row):
        if deadline is not None and time.monotonic() > deadline:
            raise ReviewValidationError("admission exceeded the 120-second transaction budget")
        if row is None:
            raise ReviewValidationError("database lineage entity is missing")
        records[f"{row.__tablename__}:{row.id}"] = _record(row)
        return row

    def snapshot(snapshot_id, source):
        key = (snapshot_id, source["legacy_document_id"])
        if key in snapshots:
            return snapshots[key]
        snap = remember(db.get(LegalSourceSnapshot, snapshot_id))
        _equal(snap.source_url, source["api_url"], "snapshot URL")
        blob = db.get(LegalSourceBlob, snap.blob_sha256)
        if blob is None:
            raise ReviewValidationError("database evidence blob is missing")
        raw = bytes(blob.payload)
        _equal(len(raw), blob.byte_length, "blob length")
        _equal(hashlib.sha256(raw).hexdigest(), snap.blob_sha256, "blob SHA-256")
        _, normalized, _ = validate_official_api_bytes(
            raw, source=parse_workspace_source_url(source["workspace_url"]),
            expected_legacy_md5=source["legacy_md5"],
            expected_legacy_full_text_md5=source["legacy_full_text_md5"],
            expected_legacy_compact_md5=source["legacy_compact_md5"],
            legacy_normalizer=source["legacy_normalizer"],
        )
        # Metadata-only observations are accepted; legal text must match exactly.
        _equal(normalized, texts[source["legacy_document_id"]], "archived normalized source text")
        entities.add(("source_snapshot", snap.id))
        snapshots[key] = snap
        return snap

    def act_publication(source):
        act = remember(db.query(LegalAct).filter_by(legacy_document_id=UUID(source["legacy_document_id"])).one_or_none())
        _equal(act.canonical_key, f"ge:infohub:{source['unique_key']}", "act canonical identity")
        _equal(act.canonical_source_url, source["workspace_url"], "act URL")
        _equal(act.official_title_ka, source["title"], "act title")
        pub = remember(db.query(LegalActPublication).filter_by(
            legal_act_id=act.id, publication_key=f"infohub:{source['unique_key']}",
        ).one_or_none())
        _equal(pub.official_url, source["workspace_url"], "publication URL")
        _equal(pub.is_consolidated, False, "publication is not a consolidation")
        snapshot(pub.source_snapshot_id, source)
        current = db.query(LegalSourceSnapshot).filter_by(
            source_url=source["api_url"], blob_sha256=source["content_sha256"],
        ).one_or_none()
        if current is None:
            raise ReviewValidationError("reviewed source observation is not in the database")
        snapshot(current.id, source)
        observation = remember(db.query(LegalSourceObservation).filter_by(
            snapshot_id=current.id, observed_at=parse_iso_datetime(source["captured_at_utc"]),
        ).one_or_none())
        _equal(observation.http_status, source["http_status"], "source observation HTTP status")
        for field, value in {"backfill_contract": BACKFILL_CONTRACT,
                             "legacy_document_id": source["legacy_document_id"],
                             "workspace_url": source["workspace_url"],
                             "legacy_normalizer": source["legacy_normalizer"],
                             "verification_mode": source["verification_mode"]}.items():
            _equal((observation.metadata_json or {}).get(field), value, "source observation " + field)
        entities.update({("act", act.id), ("publication", pub.id)})
        return act, pub

    for row in plan["rows"]:
        evidence = row["evidence"]
        source = source_by_id[evidence["amendment_source"]["legacy_document_id"]]
        target = source_by_id[evidence["target_source"]["legacy_document_id"]]
        _, pub = act_publication(source)
        act, _ = act_publication(target)
        provision = remember(db.query(LegalProvision).filter_by(
            legal_act_id=act.id, stable_key=f"article:{evidence['classification']['article_ref']}",
        ).one_or_none())
        _equal(provision.ordinal_path, evidence["classification"]["article_ref"], "article ordinal")
        _equal(provision.provision_type, "article", "provision type")
        if db.query(LegalProvisionVersion.id).filter_by(provision_id=provision.id).first():
            raise ReviewValidationError("target already has provision versions; dedicated lifecycle review required")
        fingerprint = evidence["candidate_fingerprint"]
        found = db.query(LegalAmendmentOperation).filter(
            LegalAmendmentOperation.structured_payload["legacy_candidate_fingerprint"].as_string() == fingerprint,
        ).all()
        if len(found) != 1:
            raise ReviewValidationError("candidate fingerprint must map to exactly one operation")
        op = remember(found[0])
        candidate = candidates[fingerprint]
        payload = op.structured_payload
        for field, value in {
            "backfill_contract": BACKFILL_CONTRACT, "review_state": "needs_expert_review",
            "authoritative_text_promoted": False,
            "legacy_law_amendment_id": evidence["legacy_law_amendment_id"],
            "legacy_candidate_fingerprint": fingerprint,
            "legacy_extraction_version": candidate["legacy_extraction_version"],
            "legacy_action": candidate["legacy_action"],
            "source_verification_mode": source["verification_mode"],
            "article_mention_count": candidate["classification"]["article_mention_count"],
            "operative_marker_codes": candidate["classification"]["marker_codes"],
        }.items():
            _equal(payload.get(field), value, field)
        for actual, expected, label in (
            (op.amendment_publication_id, pub.id, "amendment publication"),
            (op.target_provision_id, provision.id, "target provision"),
            (op.operation_type, candidate["classification"]["operation_type"], "operation type"),
            (op.effective_from, parse_iso_date(evidence["effective_date"]), "effective date"),
            (op.effective_to, None, "effective end"),
            (op.supersedes_operation_id, None, "superseded operation"),
            (op.source_locator, source["workspace_url"], "operation locator"),
            (op.extraction_method, "llm_assisted", "extraction method"),
        ):
            _equal(actual, expected, label)
        if db.query(LegalAmendmentOperation.id).filter_by(supersedes_operation_id=op.id).first():
            raise ReviewValidationError("operation has already been superseded")
        snap = snapshot(op.source_snapshot_id, source)
        _equal(snap.blob_sha256, payload.get("source_blob_sha256"), "operation evidence SHA-256")
        _equal(op.operation_key, operation_key(candidate, snap.blob_sha256), "operation key")
        entities.update({("provision", provision.id), ("amendment_operation", op.id)})
        event_specs.append({
            "id": uuid5(NAMESPACE_URL, f"{ADMISSION_CONTRACT}:{op.id}"),
            "entity_type": "amendment_operation", "entity_id": op.id,
            "event_type": "expert_verified" if row["decision"]["state"] == "confirm" else "rejected",
            "reviewer": row["independent_review"]["reviewer"].strip(),
            "rationale": canonical_json_bytes({
                "contract": ADMISSION_CONTRACT, "admission_sha256": plan["admission_sha256"],
                "proposal_sha256": plan["proposal_sha256"],
                "independent_review_sha256": plan["independent_review_sha256"], "row": row,
                "authoritative_text_promoted": False,
            }).decode(),
            "evidence_locator": row["decision"]["evidence_locator"],
        })

    if len({event["entity_id"] for event in event_specs}) != len(event_specs):
        raise ReviewValidationError("multiple decisions target the same operation")
    by_operation = {event["entity_id"]: event for event in event_specs}
    reused = set()
    for entity_type, entity_id in sorted(entities, key=lambda e: (e[0], str(e[1]))):
        events = db.query(LegalReviewEvent).filter_by(entity_type=entity_type, entity_id=entity_id).all()
        if entity_type == "amendment_operation" and not {"machine_extracted", "needs_review"} <= {e.event_type for e in events}:
            raise ReviewValidationError("operation lacks its machine/pending review history")
        for event in events:
            remember(event)
            spec = by_operation.get(entity_id) if entity_type == "amendment_operation" else None
            if spec and event.id == spec["id"]:
                for key, value in spec.items():
                    _equal(getattr(event, key), value, "existing admission event")
                reused.add(event.id)
            elif event.event_type not in {"machine_extracted", "needs_review"} or event.reviewer:
                raise ReviewValidationError("conflicting human/lifecycle review event exists")
    scope_sha = sha256_json({"schema": installed, "records": records})
    return scope_sha, event_specs, reused


def execute_admission(session_factory, manifest, texts, plan, *, mode="preflight",
                      max_events=0, recovery=None, rollback_proof=None):
    if mode not in {"preflight", "rehearse", "apply"}:
        raise ReviewValidationError("unknown admission mode")
    if not 1 <= len(plan["rows"]) <= MAX_ADMISSIONS:
        raise ReviewValidationError("admission requires 1..100 rows")
    if mode != "preflight" and (type(max_events) is not int or max_events != len(plan["rows"])):
        raise ReviewValidationError("--max-events must equal the exact reviewed row count")
    if mode != "preflight" and not recovery:
        raise ReviewValidationError("verified backup/restore evidence is required")
    if mode == "apply":
        validate_rollback_proof(rollback_proof, plan, recovery)
    db = session_factory()
    try:
        if db.get_bind().dialect.name != "postgresql":
            raise ReviewValidationError("review admission requires PostgreSQL")
        db.begin()
        if mode == "preflight":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        db.execute(text("SET LOCAL idle_in_transaction_session_timeout = '120s'"))
        deadline = time.monotonic() + 120
        if mode != "preflight":
            db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": BACKFILL_CONTRACT})
            # Serialize even writers which do not use our advisory-lock key.
            db.execute(text("LOCK TABLE legal_acts, legal_act_publications, legal_provisions, legal_provision_versions, legal_amendment_operations, legal_source_snapshots, legal_source_blobs, legal_source_observations, legal_temporal_schema_migrations IN SHARE MODE"))
            db.execute(text("LOCK TABLE legal_review_events IN SHARE ROW EXCLUSIVE MODE"))
        scope, specs, reused = _scope(db, manifest, texts, plan, deadline=deadline)
        missing = [spec for spec in specs if spec["id"] not in reused]
        if mode == "rehearse" and reused:
            raise ReviewValidationError("rehearsal requires the pre-import restored database")
        if mode == "apply" and missing and scope != rollback_proof["scope_sha256"]:
            raise ReviewValidationError("database scope changed since rollback rehearsal")
        if mode != "preflight":
            for spec in missing:
                db.add(LegalReviewEvent(**spec))
                db.flush()
            # All IDs and payloads must resolve as exact replays before commit.
            _, _, checked = _scope(db, manifest, texts, plan, deadline=deadline)
            if len(checked) != len(specs):
                raise ReviewValidationError("post-insert event count mismatch")
        if mode == "apply":
            db.commit()
        else:
            db.rollback()
        if mode == "rehearse":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            after, _, _ = _scope(db, manifest, texts, plan)
            if after != scope:
                raise ReviewValidationError("rollback did not preserve the original scope")
            db.rollback()
            return {
                "contract": ADMISSION_CONTRACT, "admission_sha256": plan["admission_sha256"],
                **recovery, "scope_sha256": scope, "events_rehearsed": len(specs),
                "rolled_back": True, "completed_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        return {
            "contract": ADMISSION_CONTRACT, "admission_sha256": plan["admission_sha256"],
            "scope_sha256": scope, "events": len(specs), "events_reused": len(reused),
            "events_to_create": len(missing) if mode == "preflight" else 0,
            "events_created": len(missing) if mode == "apply" else 0,
            "transaction_result": "committed" if mode == "apply" else "read_only",
            "database_writes_allowed": mode == "apply", "authoritative_versions_created": 0,
            "public_answer_routing_changed": False,
        }
    finally:
        db.rollback()
        db.close()
