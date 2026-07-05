"""
Public catalog of situational guides (სიტუაციური სახელმძღვანელო) —
the Revenue Service's numbered how-to manuals on specific tax situations.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db

router = APIRouter(prefix="/guides", tags=["Guides"])

GUIDE_WHERE = r"document_type = 'guideline' AND title ~ 'N ?[0-9]{3,5}\s*$'"


@router.get("")
def list_guides(
    search: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    params = {}
    where = GUIDE_WHERE
    if search:
        where += " AND title ILIKE :search"
        params["search"] = f"%{search}%"
    total = db.execute(text(f"SELECT count(*) FROM documents WHERE {where}"), params).scalar()
    rows = db.execute(text(f"""
        SELECT id::text, title,
               substring(title FROM 'N ?([0-9]+)\\s*$') AS guide_number,
               date_published, source_url
        FROM documents WHERE {where}
        ORDER BY substring(title FROM 'N ?([0-9]+)\\s*$')::int DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset}).all()
    return {
        "total": total,
        "items": [
            {
                "id": r[0],
                "title": r[1],
                "number": r[2],
                "date_published": r[3].isoformat() if r[3] else None,
                "source_url": r[4],
            }
            for r in rows
        ],
    }
