"""
Bug reports / feedback from the client cabinet.

Stored in the DB and forwarded to Gela's Telegram (same bot the scraper
alerts use) on a best-effort basis.
"""
import logging
import os
from typing import Optional

import requests
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.plans import get_active_plan
from core.security import get_current_user
from models import Feedback, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["Feedback"])


class FeedbackCreate(BaseModel):
    message: str = Field(min_length=5, max_length=4000)
    page: Optional[str] = Field(default=None, max_length=300)


def _notify_telegram(email: str, plan: str, message: str, page: Optional[str]) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.info("Feedback saved; Telegram creds absent, notification skipped")
        return
    text = f"🐞 tax-advisor.ge — новый багрепорт\nОт: {email} ({plan})"
    if page:
        text += f"\nСтраница: {page}"
    text += f"\n\n{message}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001 — notification must never fail the request
        logger.warning("Feedback Telegram notification failed: %s", exc)


@router.post("", status_code=201)
def create_feedback(
    body: FeedbackCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = Feedback(user_id=current_user.id, message=body.message.strip(), page=body.page)
    db.add(item)
    db.commit()
    background_tasks.add_task(
        _notify_telegram, current_user.email, get_active_plan(db, current_user), item.message, item.page
    )
    return {"id": str(item.id), "status": "received"}
