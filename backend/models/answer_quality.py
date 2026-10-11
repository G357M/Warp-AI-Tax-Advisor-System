"""
User ratings of assistant answers and append-only admin reviews.

Installed by scripts/add_answer_quality.py; reviews are protected by triggers.
Types are portable (JSON, not JSONB/ARRAY) so the SQLite integration tests can create them.
"""
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base
from core.time_utils import utc_now


class AnswerRating(Base):
    __tablename__ = "answer_ratings"
    __table_args__ = (UniqueConstraint("message_id", name="uq_answer_ratings_message"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    value = Column(SmallInteger, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class AnswerReview(Base):
    __tablename__ = "answer_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    # No FK: removing an admin account must not rewrite review history.
    reviewer_id = Column(UUID(as_uuid=True), nullable=False)
    verdict = Column(String(16), nullable=False)
    reasons = Column(JSON, nullable=False, default=list)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
