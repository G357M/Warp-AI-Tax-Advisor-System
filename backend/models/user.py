"""
SQLAlchemy models for users and authentication.
"""
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base
from core.time_utils import utc_now


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False, default="user")  # guest | user | admin
    is_active = Column(Boolean, default=True, nullable=False)
    email_verified_at = Column(DateTime, nullable=True)
    session_version = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    last_login = Column(DateTime, nullable=True)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class AuthActionToken(Base):
    """Hashed, one-time credential for an account recovery action."""

    __tablename__ = "auth_action_tokens"
    __table_args__ = (
        Index(
            "ix_auth_action_tokens_user_purpose_created",
            "user_id",
            "purpose",
            "created_at",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose = Column(String(32), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
