"""Real PostgreSQL proof in CI only. All decisions and dumps are fixtures."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
import json
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from core.database import engine
from legal_temporal.backfill import candidate_fingerprint, manifest_sha256, normalized_infohub_text
from legal_temporal.expert_review import ReviewValidationError, load_evidence
from legal_temporal.review_importer import execute_admission
from models.document import Document, LawAmendment
from models.legal_temporal import (
    LegalAct, LegalAmendmentOperation, LegalProvisionVersion, LegalReviewEvent,
)
from scripts.import_legal_temporal_backfill import apply_bundle
from test_legal_temporal_expert_review import evidence  # noqa: F401
from test_legal_temporal_review_admission import _admission

pytestmark = pytest.mark.skipif(os.getenv("LEGAL_TEMPORAL_POSTGRES_TESTS") != "1",
                                reason="requires disposable CI PostgreSQL")
RECOVERY = {"backup_sha256": "c" * 64, "restore_evidence_sha256": "d" * 64}


@pytest.fixture
def admitted_fixture(evidence):
    bundle, manifest, texts = evidence
    # Two candidates permit a failure after the first real INSERT.
    amendment = manifest["amendments"][0]
    second = deepcopy(amendment["candidates"][0])
    second["item_index"] = 1
    second["candidate_fingerprint"] = candidate_fingerprint(second)
    amendment["candidates"].append(second)
    for key in ("candidate_items", "operation_candidates", "expert_review_rows"):
        manifest["summary"][key] = 2
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    manifest, texts = load_evidence(bundle, manifest["manifest_sha256"])
    with Session(engine) as db:
        for source in manifest["sources"]:
            db.add(Document(id=UUID(source["legacy_document_id"]), title=source["title"],
                document_type="law", language="ka", status="active", source_url=source["workspace_url"],
                file_hash=source["legacy_md5"], full_text=texts[source["legacy_document_id"]], metadata_json={}))
        db.flush()
        db.add(LawAmendment(id=UUID(amendment["legacy_law_amendment_id"]),
            amendment_doc_id=UUID(amendment["amendment_legacy_document_id"]),
            target_law_doc_id=UUID(amendment["target_legacy_document_id"]), target_law_title="Fixture",
            adoption_date=date(2026, 1, 1), effective_date=date(2026, 2, 1), status="in_force",
            affected_articles=[{"article": "5", "action": "added"}], extraction_version=1))
        db.commit()
    apply_bundle(bundle_dir=bundle, manifest=manifest, max_source_snapshots=2, max_acts=2, max_operations=2)
    # Approve both rows explicitly with fixture reviewers, not real humans.
    from test_legal_temporal_expert_review import _document, _decision, _validate, NOW
    from test_legal_temporal_review_admission import _second
    from legal_temporal.review_admission import validate_admission
    document = _document(manifest, texts)
    document["rows"][1]["decision"] = _decision()
    proposals = _validate(manifest, texts, document)
    plan = validate_admission(proposals, _second(proposals), "b" * 64, now=NOW)
    factory = sessionmaker(bind=engine, autoflush=False)
    return bundle, manifest, texts, plan, factory


def _run(data, **kwargs):
    _, manifest, texts, plan, factory = data
    return execute_admission(factory, manifest, texts, plan, **kwargs)


def _human_events(data):
    fingerprints = [r["evidence"]["candidate_fingerprint"] for r in data[3]["rows"]]
    with Session(engine) as db:
        ids = [op.id for op in db.query(LegalAmendmentOperation).filter(
            LegalAmendmentOperation.structured_payload["legacy_candidate_fingerprint"].as_string().in_(fingerprints))]
        return db.query(LegalReviewEvent).filter(LegalReviewEvent.entity_id.in_(ids),
            LegalReviewEvent.event_type.in_(["expert_verified", "rejected"])).count()


def test_readonly_rehearsal_apply_and_idempotent_replay(admitted_fixture):
    data = admitted_fixture
    before = _run(data)
    assert before["events_to_create"] == 2
    assert before["database_writes_allowed"] is False
    assert _human_events(data) == 0
    proof = _run(data, mode="rehearse", max_events=2, recovery=RECOVERY)
    assert proof["rolled_back"] is True
    assert proof["scope_sha256"] == before["scope_sha256"]
    assert _human_events(data) == 0
    applied = _run(data, mode="apply", max_events=2, recovery=RECOVERY, rollback_proof=proof)
    assert applied["events_created"] == 2
    assert _human_events(data) == 2
    repeated = _run(data, mode="apply", max_events=2, recovery=RECOVERY, rollback_proof=proof)
    assert repeated["events_created"] == 0
    assert repeated["events_reused"] == 2
    with Session(engine) as db:
        assert db.query(LegalProvisionVersion).count() == 0
        assert db.query(LegalReviewEvent).filter_by(event_type="published").count() == 0


@pytest.mark.parametrize("mode", ["rehearse", "apply"])
def test_mid_transaction_failure_leaves_no_partial_approval(admitted_fixture, mode):
    class FailAfterFirstInsert(Session):
        def flush(self, *args, **kwargs):
            pending = [row for row in self.new if isinstance(row, LegalReviewEvent)]
            result = super().flush(*args, **kwargs)
            if pending:
                raise RuntimeError("fixture interruption after real INSERT")
            return result

    data = admitted_fixture
    before = _run(data)
    proof = _run(data, mode="rehearse", max_events=2, recovery=RECOVERY)
    failing = (*data[:4], sessionmaker(bind=engine, class_=FailAfterFirstInsert, autoflush=False))
    with pytest.raises(RuntimeError, match="real INSERT"):
        _run(failing, mode=mode, max_events=2, recovery=RECOVERY, rollback_proof=proof)
    assert _human_events(data) == 0
    assert _run(data)["scope_sha256"] == before["scope_sha256"]


def test_concurrent_identical_imports_create_each_event_once(admitted_fixture):
    from threading import Barrier
    data = admitted_fixture
    proof = _run(data, mode="rehearse", max_events=2, recovery=RECOVERY)
    barrier = Barrier(2)

    def apply_once():
        barrier.wait(timeout=10)
        return _run(data, mode="apply", max_events=2, recovery=RECOVERY, rollback_proof=proof)

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(apply_once) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    assert sorted(result["events_created"] for result in results) == [0, 2]
    assert _human_events(data) == 2


@pytest.mark.parametrize("max_events", [0, 1, 3, True])
def test_exact_ceilings_before_any_write(admitted_fixture, max_events):
    with pytest.raises(ReviewValidationError, match="exact"):
        _run(admitted_fixture, mode="rehearse", max_events=max_events, recovery=RECOVERY)
    assert _human_events(admitted_fixture) == 0


def test_stale_scope_refuses_entire_import(admitted_fixture):
    data = admitted_fixture
    proof = _run(data, mode="rehearse", max_events=2, recovery=RECOVERY)
    with Session(engine) as db:
        act = db.query(LegalAct).filter_by(legacy_document_id=UUID(data[1]["sources"][0]["legacy_document_id"])).one()
        act.document_number = "changed after rehearsal"
        db.commit()
    with pytest.raises(ReviewValidationError, match="scope changed"):
        _run(data, mode="apply", max_events=2, recovery=RECOVERY, rollback_proof=proof)
    assert _human_events(data) == 0


@pytest.mark.parametrize("change", ["url", "duplicate_fingerprint", "human_event", "superseded"])
def test_lineage_or_lifecycle_conflicts_stop_admission(admitted_fixture, change):
    data = admitted_fixture
    with Session(engine) as db:
        fingerprint = data[3]["rows"][0]["evidence"]["candidate_fingerprint"]
        op = db.query(LegalAmendmentOperation).filter(
            LegalAmendmentOperation.structured_payload["legacy_candidate_fingerprint"].as_string() == fingerprint).one()
        if change == "url":
            db.query(LegalAct).filter_by(legacy_document_id=UUID(data[1]["sources"][0]["legacy_document_id"])).one().canonical_source_url = "https://example.invalid"
        elif change == "human_event":
            db.add(LegalReviewEvent(entity_type="amendment_operation", entity_id=op.id,
                event_type="withdrawn", reviewer="Lifecycle fixture", rationale="fixture only"))
        else:
            copied = {c.name: getattr(op, c.name) for c in op.__table__.columns if c.name not in {"id", "recorded_at", "operation_key"}}
            if change == "superseded":
                copied["supersedes_operation_id"] = op.id
                copied["structured_payload"] = copied["structured_payload"] | {"legacy_candidate_fingerprint": "f" * 64}
            db.add(LegalAmendmentOperation(**copied, operation_key=hashlib.sha256(uuid4().bytes).hexdigest()))
        db.commit()
    with pytest.raises(ReviewValidationError):
        _run(data, mode="rehearse", max_events=2, recovery=RECOVERY)
    assert _human_events(data) == 0


def test_metadata_only_new_observation_preserves_original_anchor(admitted_fixture):
    bundle, manifest, texts, plan, factory = admitted_fixture
    source = manifest["sources"][0]
    payload = json.loads((bundle / source["file"]).read_bytes())
    payload["views"] = 456
    raw = json.dumps(payload, ensure_ascii=False).encode()
    source.update({"file": "sources/new-observation.json", "byte_length": len(raw),
                   "content_sha256": hashlib.sha256(raw).hexdigest()})
    (bundle / source["file"]).write_bytes(raw)
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    observed, texts = load_evidence(bundle, manifest["manifest_sha256"])
    apply_bundle(bundle_dir=bundle, manifest=observed, max_source_snapshots=2, max_acts=2, max_operations=2)
    # A separately revalidated single proposal suffices to test old anchor reuse.
    plan = _admission(observed, texts)
    report = execute_admission(factory, observed, texts, plan)
    assert report["events_to_create"] == 1


def test_conflicting_resubmission_is_not_an_idempotent_replay(admitted_fixture):
    data = admitted_fixture
    proof = _run(data, mode="rehearse", max_events=2, recovery=RECOVERY)
    _run(data, mode="apply", max_events=2, recovery=RECOVERY, rollback_proof=proof)
    changed = deepcopy(data[3])
    changed["rows"][0]["decision"]["state"] = "reject"
    with pytest.raises(ReviewValidationError, match="existing admission event"):
        _run((*data[:3], changed, data[4]))


def test_readonly_preflight_cannot_insert_even_accidentally(admitted_fixture, monkeypatch):
    import legal_temporal.review_importer as importer
    original = importer._scope

    def attempted_write(db, *args, **kwargs):
        scope, specs, reused = original(db, *args, **kwargs)
        db.add(LegalReviewEvent(**specs[0]))
        db.flush()
        return scope, specs, reused

    monkeypatch.setattr(importer, "_scope", attempted_write)
    from sqlalchemy.exc import InternalError
    with pytest.raises(InternalError, match="read-only"):
        _run(admitted_fixture)
    assert _human_events(admitted_fixture) == 0
