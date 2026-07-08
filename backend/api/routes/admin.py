"""
Admin API: real system stats, document/user management, ops visibility.
All endpoints require the admin role.
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import require_admin
from models import Feedback, User

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


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
    return {
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


@router.get("/users")
def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    total = db.execute(text("SELECT count(*) FROM users")).scalar()
    rows = db.execute(text("""
        SELECT u.id::text, u.username, u.email, u.role, u.created_at, u.last_login,
               s.plan, s.status, s.period_end
        FROM users u
        LEFT JOIN subscriptions s ON s.user_id = u.id
        ORDER BY u.created_at DESC
        LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).all()
    now = datetime.utcnow()
    items = []
    for r in rows:
        plan = "free"
        if r[3] == "admin":
            plan = "business"
        elif r[6] and r[7] == "active" and (r[8] is None or r[8] >= now):
            plan = r[6]
        items.append({
            "id": r[0], "username": r[1], "email": r[2], "role": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
            "last_login": r[5].isoformat() if r[5] else None,
            "plan": plan,
            "period_end": r[8].isoformat() if r[8] else None,
        })
    return {"total": total, "items": items}


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|admin)$")


@router.patch("/users/{user_id}/role")
def update_user_role(
    user_id: UUID,
    body: RoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if user_id == admin.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="Нельзя снять права администратора с самого себя.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = body.role
    db.commit()
    return {"id": str(user.id), "username": user.username, "role": user.role}


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
            "law_amendments_backfill": _tail("/tmp/law_amendments_backfill.log"),
            "decision_facts_backfill": _tail("/tmp/decision_facts_backfill.log"),
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


@router.patch("/feedback/{feedback_id}")
def update_feedback_status(
    feedback_id: UUID,
    body: FeedbackStatusUpdate,
    db: Session = Depends(get_db),
):
    item = db.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")
    item.status = body.status
    db.commit()
    return {"id": str(item.id), "status": item.status}
