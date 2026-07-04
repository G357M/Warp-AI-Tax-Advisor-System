"""
Client cabinet: profile and usage.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.plans import get_active_plan, questions_used_today, FREE_DAILY_QUESTIONS
from core.security import get_current_user
from models import User

router = APIRouter(prefix="/account", tags=["Account"])


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)


@router.get("")
def my_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = get_active_plan(db, current_user)
    used = questions_used_today(current_user.id)
    return {
        "email": current_user.email,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "plan": plan,
        "usage": {
            "questions_today": used,
            "daily_limit": FREE_DAILY_QUESTIONS if plan == "free" else None,
        },
    }


@router.patch("")
def update_account(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name.strip() or None
    db.commit()
    return {"full_name": current_user.full_name}
