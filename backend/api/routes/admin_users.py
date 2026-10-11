"""Admin client management: search, the user card and journaled account actions.
All endpoints require the admin role."""
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.admin_users import admin_error, list_users_page, user_card
from core.database import get_db
from core.security import require_admin
from models import User

router = APIRouter(prefix="/admin/users", tags=["Admin"], dependencies=[Depends(require_admin)])

PlanFilter = Literal["free", "pro", "business", "expiring"]
StatusFilter = Literal["active", "blocked", "unverified", "admin"]
UserSort = Literal["created_desc", "last_login_desc", "period_end_asc"]


@router.get("")
def list_users(
    q: Optional[str] = Query(default=None, max_length=100),
    plan: Optional[PlanFilter] = None,
    status: Optional[StatusFilter] = None,
    sort: UserSort = "created_desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return list_users_page(db, q=q, plan=plan, status=status, sort=sort, limit=limit, offset=offset)


def locked_user(db: Session, user_id: UUID) -> User:
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise admin_error(404, "user_not_found", "User not found")
    return user


@router.get("/{user_id}", responses={404: {"description": "User not found"}})
def get_user_card(user_id: UUID, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise admin_error(404, "user_not_found", "User not found")
    return user_card(db, user)
