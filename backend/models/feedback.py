"""
SQLAlchemy model for user bug reports / feedback from the client cabinet.
"""
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base
from core.time_utils import utc_now


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message = Column(Text, nullable=False)
    page = Column(String(300), nullable=True)  # URL/path where the problem occurred
    status = Column(String(20), nullable=False, default="new")  # new | in_progress | fixed

    created_at = Column(DateTime, default=utc_now, nullable=False)

    user = relationship("User")
