"""
SQLAlchemy models for subscriptions and payments.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, Boolean, Float, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    plan = Column(String(20), nullable=False, default="free")      # free | pro | business
    status = Column(String(20), nullable=False, default="active")  # active | past_due | canceled
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    auto_renew = Column(Boolean, nullable=False, default=False)
    payment_provider = Column(String(20), nullable=True)           # manual | bog
    external_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User")
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    amount_gel = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="GEL")
    provider = Column(String(20), nullable=False)                  # manual | bog
    provider_tx_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="succeeded")  # succeeded | pending | failed
    raw_webhook = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    subscription = relationship("Subscription", back_populates="payments")


Index("idx_payments_subscription", Payment.subscription_id)
Index("idx_payments_provider_tx", Payment.provider_tx_id)
