"""
SQLAlchemy model for user bug reports / feedback from the client cabinet.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message = Column(Text, nullable=False)
    page = Column(String(300), nullable=True)  # URL/path where the problem occurred

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")
