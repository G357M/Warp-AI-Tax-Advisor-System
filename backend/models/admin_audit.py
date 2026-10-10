"""
Append-only journal of administrator actions.

Rows are inserted in the same transaction as the change they describe and are
never updated or deleted (enforced by a PostgreSQL trigger installed by
scripts/add_admin_audit_log.py).
"""
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base
from core.time_utils import utc_now


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("ix_admin_audit_created", "created_at"),
        Index("ix_admin_audit_action_created", "action", "created_at"),
        Index("ix_admin_audit_actor_created", "actor_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    # No FK: removing an account must not rewrite or block the journal.
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), nullable=False)
    target_id = Column(String(64), nullable=False)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
