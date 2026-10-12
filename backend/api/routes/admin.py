"""
Admin API: real system stats, document/user management, ops visibility.
All endpoints require the admin role.
"""
import os
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from billing.reconciliation import reconciliation_queue_filter
from core.admin_audit import record_admin_action
from core.admin_quality import down_unreviewed
from core.admin_users import admin_error
from core.database import get_db
from core.public_config import public_config
from core.security import require_admin
from core.time_utils import utc_now
from models import AdminAuditLog, BillingCheckout, Feedback, User

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])

INGEST_STALE_HOURS = 36

# Operator backfill logs are written by hand (nohup ... > <dir>/<name>.log); on Linux this is /tmp.
LOG_DIR = Path(os.environ.get("ADMIN_OPS_LOG_DIR", tempfile.gettempdir()))


@router.get("/stats")
def system_stats(db: Session = Depends(get_db)):
    docs = db.execute(text("""
        SELECT document_type, count(*) FROM documents GROUP BY 1 ORDER BY 2 DESC
    """)).all()
    last_ingest = db.execute(text("SELECT max(created_at) FROM documents")).scalar()
    decisions = db.execute(text("""
        SELECT
          (SELECT count(*) FROM documents WHERE document_type='court_decision'
             AND (metadata->>'kind') IS DISTINCT FROM 'digest') AS total,
          (SELECT count(*) FROM decision_facts) AS extracted
    """)).one()
    amendments = db.execute(text("""
        SELECT
          (SELECT count(*) FROM documents WHERE document_type='law' AND title ILIKE '%ცვლილებ%') AS acts_total,
          (SELECT count(*) FROM law_amendments) AS extracted,
          (SELECT count(*) FROM law_amendments WHERE target_law_doc_id IS NOT NULL) AS resolved
    """)).one()
    users = db.execute(text("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE role = 'admin') AS admins
        FROM users
    """)).one()
    subs = db.execute(text("""
        SELECT plan, count(*) FROM subscriptions
        WHERE status = 'active' AND (period_end IS NULL OR period_end >= now())
        GROUP BY 1
    """)).all()
    convs = db.execute(text("""
        SELECT
          (SELECT count(*) FROM conversations) AS conversations,
          (SELECT count(*) FROM messages) AS messages,
          (SELECT count(*) FROM messages WHERE created_at >= now() - interval '7 days') AS messages_7d
    """)).one()
    feedback_new = db.query(func.count(Feedback.id)).filter(Feedback.status == "new").scalar()
    reconciliation_open = db.query(func.count(BillingCheckout.id)).filter(reconciliation_queue_filter()).scalar()
    manual_pending = db.query(func.count(BillingCheckout.id)).filter(
        BillingCheckout.provider == "manual",
        BillingCheckout.status == "pending",
        BillingCheckout.expires_at >= utc_now(),
    ).scalar()
    ingest_stale = last_ingest is None or last_ingest < utc_now() - timedelta(hours=INGEST_STALE_HOURS)
    return {
        "quality": {"down_unreviewed": down_unreviewed(db)},
        "documents": {
            "total": sum(r[1] for r in docs),
            "by_type": {r[0]: r[1] for r in docs},
            "last_ingest": last_ingest.isoformat() if last_ingest else None,
        },
        "decisions": {
            "total": decisions.total,
            "extracted": decisions.extracted,
            "pending": max(decisions.total - decisions.extracted, 0),
        },
        "amendments": {
            "acts_total": amendments.acts_total,
            "extracted": amendments.extracted,
            "resolved": amendments.resolved,
            "pending": max(amendments.acts_total - amendments.extracted, 0),
        },
        "users": {"total": users.total, "admins": users.admins},
        "subscriptions": {r[0]: r[1] for r in subs},
        "conversations": {
            "total": convs.conversations,
            "messages": convs.messages,
            "messages_7d": convs.messages_7d,
        },
        "feedback": {"new": feedback_new},
        "billing": {"reconciliation_open": reconciliation_open, "manual_pending": manual_pending},
        "attention": {"ingest_stale": ingest_stale},
    }


@router.get("/documents")
def list_documents(
    search: Optional[str] = Query(default=None, max_length=200),
    doc_type: Optional[str] = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    clauses, params = ["1=1"], {}
    if search:
        clauses.append("(title ILIKE :search OR document_number ILIKE :search)")
        params["search"] = f"%{search}%"
    if doc_type:
        clauses.append("document_type = :doc_type")
        params["doc_type"] = doc_type
    where = " AND ".join(clauses)
    total = db.execute(text(f"SELECT count(*) FROM documents WHERE {where}"), params).scalar()
    rows = db.execute(text(f"""
        SELECT id::text, title, document_type, document_number, date_published,
               authority, source_url, created_at
        FROM documents WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}).all()
    return {
        "total": total,
        "items": [
            {
                "id": r[0], "title": r[1], "document_type": r[2],
                "document_number": r[3],
                "date_published": r[4].isoformat() if r[4] else None,
                "authority": r[5], "source_url": r[6],
                "created_at": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ],
    }


def _tail(path: str, lines: int = 12) -> list:
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return content[-lines:]
    except Exception:
        return []


@router.get("/ops")
def ops_status(db: Session = Depends(get_db)):
    last_ingest = db.execute(text("SELECT max(created_at) FROM documents")).scalar()
    docs_today = db.execute(text(
        "SELECT count(*) FROM documents WHERE created_at >= date_trunc('day', now())"
    )).scalar()
    pending = db.execute(text("""
        SELECT
          (SELECT count(*) FROM documents d LEFT JOIN decision_facts f ON f.document_id = d.id
             WHERE d.document_type='court_decision' AND f.id IS NULL
               AND (d.metadata->>'kind') IS DISTINCT FROM 'digest') AS decisions_pending,
          (SELECT count(*) FROM documents d LEFT JOIN law_amendments a ON a.amendment_doc_id = d.id
             WHERE d.document_type='law' AND d.title ILIKE '%ცვლილებ%' AND a.id IS NULL) AS amendments_pending
    """)).one()
    return {
        "last_ingest": last_ingest.isoformat() if last_ingest else None,
        "documents_today": docs_today,
        "pending": {
            "decision_facts": pending.decisions_pending,
            "law_amendments": pending.amendments_pending,
        },
        "logs": {
            "scraper": _tail("/app/logs/scraper.log"),
            "law_amendments_backfill": _tail(str(LOG_DIR / "law_amendments_backfill.log")),
            "decision_facts_backfill": _tail(str(LOG_DIR / "decision_facts_backfill.log")),
        },
    }


@router.get("/feedback")
def list_feedback(
    status: Optional[str] = Query(default=None, pattern="^(new|in_progress|fixed)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    where = "WHERE f.status = :status" if status else ""
    params = {"status": status} if status else {}
    total = db.execute(text(f"SELECT count(*) FROM feedback f {where}"), params).scalar()
    counts = dict(db.execute(text("SELECT status, count(*) FROM feedback GROUP BY status")).all())
    rows = db.execute(text(f"""
        SELECT f.id::text, f.message, f.page, f.status, f.created_at, u.email, u.username
        FROM feedback f JOIN users u ON u.id = f.user_id
        {where}
        ORDER BY f.created_at DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}).all()
    return {
        "total": total,
        "counts": {s: counts.get(s, 0) for s in ("new", "in_progress", "fixed")},
        "items": [
            {
                "id": r[0], "message": r[1], "page": r[2], "status": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
                "email": r[5], "username": r[6],
            }
            for r in rows
        ],
    }


class FeedbackStatusUpdate(BaseModel):
    status: str = Field(pattern="^(new|in_progress|fixed)$")
    reason: Optional[str] = Field(default=None, max_length=1000)


@router.patch("/feedback/{feedback_id}", responses={404: {"description": "Feedback not found"}})
def update_feedback_status(
    feedback_id: UUID,
    body: FeedbackStatusUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(Feedback, feedback_id)
    if not item:
        raise admin_error(404, "feedback_not_found", "Feedback not found")
    if item.status != body.status:
        before = {"status": item.status}
        item.status = body.status
        record_admin_action(db, actor=admin, action="feedback.status_changed", target_type="feedback",
                            target_id=item.id, before=before, after={"status": item.status}, reason=body.reason)
        db.commit()
    return {"id": str(item.id), "status": item.status}


@router.get("/audit")
def list_audit(
    action: Optional[str] = Query(default=None, max_length=64),
    actor_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(AdminAuditLog, User.username).outerjoin(User, User.id == AdminAuditLog.actor_id)
    if action:
        query = query.filter(AdminAuditLog.action == action)
    if actor_id:
        query = query.filter(AdminAuditLog.actor_id == actor_id)
    total = query.count()
    rows = (query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
            .offset(offset).limit(limit).all())
    return {
        "total": total,
        "items": [
            {
                "id": str(entry.id),
                "actor": {"id": str(entry.actor_id), "username": username},
                "action": entry.action,
                "target_type": entry.target_type,
                "target_id": entry.target_id,
                "before": entry.before,
                "after": entry.after,
                "reason": entry.reason,
                "created_at": entry.created_at.isoformat(),
            }
            for entry, username in rows
        ],
    }


@router.get("/config")
def admin_config():
    return public_config()
