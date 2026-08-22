"""Issue and consume high-entropy, one-time account action tokens."""

from datetime import timedelta
import hashlib
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from core.time_utils import utc_now
from models import AuthActionToken, User


EMAIL_VERIFICATION = "email_verification"
PASSWORD_RESET = "password_reset"
ALLOWED_PURPOSES = {EMAIL_VERIFICATION, PASSWORD_RESET}


def _digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_action_token(
    db: Session,
    *,
    user: User,
    purpose: str,
    lifetime: timedelta,
    cooldown_seconds: int,
) -> Optional[str]:
    """Return a raw token once, or ``None`` while the issue cooldown is active."""
    if purpose not in ALLOWED_PURPOSES:
        raise ValueError(f"unsupported auth token purpose: {purpose}")

    now = utc_now()
    latest = (
        db.query(AuthActionToken)
        .filter(
            AuthActionToken.user_id == user.id,
            AuthActionToken.purpose == purpose,
        )
        .order_by(AuthActionToken.created_at.desc())
        .first()
    )
    if latest and (now - latest.created_at).total_seconds() < cooldown_seconds:
        return None

    db.query(AuthActionToken).filter(
        AuthActionToken.user_id == user.id,
        AuthActionToken.purpose == purpose,
        AuthActionToken.consumed_at.is_(None),
    ).update({AuthActionToken.consumed_at: now}, synchronize_session=False)

    raw_token = secrets.token_urlsafe(32)
    db.add(
        AuthActionToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=_digest(raw_token),
            expires_at=now + lifetime,
        )
    )
    return raw_token


def consume_action_token(
    db: Session,
    *,
    raw_token: str,
    purpose: str,
) -> Optional[User]:
    """Atomically consume a valid token and return its owner."""
    if purpose not in ALLOWED_PURPOSES:
        raise ValueError(f"unsupported auth token purpose: {purpose}")

    token = (
        db.query(AuthActionToken)
        .filter(
            AuthActionToken.token_hash == _digest(raw_token),
            AuthActionToken.purpose == purpose,
        )
        .with_for_update()
        .first()
    )
    now = utc_now()
    if not token or token.consumed_at is not None or token.expires_at <= now:
        return None

    token.consumed_at = now
    return db.query(User).filter(User.id == token.user_id).first()
