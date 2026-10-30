"""Record administrator actions in the append-only journal."""
from models import AdminAuditLog

ADMIN_ACTIONS = frozenset({
    "user.role_changed", "subscription.activated", "feedback.status_changed",
    "user.blocked", "user.unblocked", "subscription.granted", "subscription.canceled",
    "user.password_reset_sent", "user.verification_sent",
    "answer.reviewed", "user.identity_revealed", "ops.job_requested",
})
TARGET_TYPES = frozenset({"user", "checkout", "feedback", "message", "ops_job"})
REASON_MAX_LENGTH = 1000


def record_admin_action(db, *, actor, action, target_type, target_id,
                        before=None, after=None, reason=None) -> AdminAuditLog:
    """Add a journal row to the caller's transaction; the caller commits.

    Flushing here surfaces an insert failure before the caller commits, so the
    change and its journal row succeed or fail together.
    """
    if action not in ADMIN_ACTIONS:
        raise ValueError(f"Unknown admin action: {action}")
    if target_type not in TARGET_TYPES:
        raise ValueError(f"Unknown admin target type: {target_type}")
    cleaned = (reason or "").strip()[:REASON_MAX_LENGTH] or None
    entry = AdminAuditLog(
        actor_id=actor.id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        before=before,
        after=after,
        reason=cleaned,
    )
    db.add(entry)
    db.flush()
    return entry
