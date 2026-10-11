"""Admin client management: search, the user card and journaled account actions.
All endpoints require the admin role."""
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.admin_audit import record_admin_action
from core.admin_users import Reason, admin_error, list_users_page, user_card
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


class ReasonBody(BaseModel):
    reason: Reason


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|admin)$")
    reason: Reason


def finish(db: Session, user: User, changed: bool, **extra) -> dict:
    db.commit()
    db.refresh(user)
    return {"changed": changed, **extra, **user_card(db, user)}


@router.patch(
    "/{user_id}/role",
    responses={
        400: {"description": "Admin cannot remove their own admin role"},
        404: {"description": "User not found"},
        409: {"description": "Blocked users cannot be promoted"},
    },
)
def update_user_role(user_id: UUID, body: RoleUpdate, admin: User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    if user_id == admin.id and body.role != "admin":
        raise admin_error(400, "cannot_demote_self", "Administrators cannot remove their own admin role")
    user = locked_user(db, user_id)
    if body.role == "admin" and user.role != "admin" and not user.is_active:
        raise admin_error(409, "user_blocked", "Blocked users cannot be promoted")
    changed = user.role != body.role
    if changed:
        before = {"role": user.role}
        user.role = body.role
        record_admin_action(db, actor=admin, action="user.role_changed", target_type="user", target_id=user.id,
                            before=before, after={"role": user.role}, reason=body.reason)
    return finish(db, user, changed)


@router.post(
    "/{user_id}/block",
    responses={
        400: {"description": "Administrators cannot block themselves"},
        404: {"description": "User not found"},
        409: {"description": "Administrators must be demoted before blocking"},
    },
)
def block_user(user_id: UUID, body: ReasonBody, admin: User = Depends(require_admin),
               db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise admin_error(400, "cannot_block_self", "Administrators cannot block themselves")
    user = locked_user(db, user_id)
    if user.role == "admin":
        raise admin_error(409, "cannot_block_admin", "Remove the admin role before blocking")
    changed = user.is_active
    if changed:
        user.is_active = False
        user.session_version = (user.session_version or 0) + 1
        record_admin_action(db, actor=admin, action="user.blocked", target_type="user", target_id=user.id,
                            before={"is_active": True}, after={"is_active": False}, reason=body.reason)
    return finish(db, user, changed)


@router.post("/{user_id}/unblock", responses={404: {"description": "User not found"}})
def unblock_user(user_id: UUID, body: ReasonBody, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    user = locked_user(db, user_id)
    changed = not user.is_active
    if changed:
        user.is_active = True
        record_admin_action(db, actor=admin, action="user.unblocked", target_type="user", target_id=user.id,
                            before={"is_active": False}, after={"is_active": True}, reason=body.reason)
    return finish(db, user, changed)
