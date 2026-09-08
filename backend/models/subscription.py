"""
SQLAlchemy models for subscriptions and payments.
"""
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.database import Base
from core.time_utils import utc_now


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

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = relationship("User")
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    amount_gel = Column(Float, nullable=False)
    # Integer tetri is the payment ledger authority. amount_gel remains only as
    # a compatibility projection for older administrative/reporting code.
    amount_minor = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="GEL")
    provider = Column(String(20), nullable=False)                  # manual | bog
    provider_tx_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="succeeded")  # succeeded | pending | failed
    raw_webhook = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    subscription = relationship("Subscription", back_populates="payments")


Index("idx_payments_subscription", Payment.subscription_id)
Index("idx_payments_provider_tx", Payment.provider_tx_id)
Index("uq_payments_provider_tx", Payment.provider, Payment.provider_tx_id, unique=True)


class BillingCheckout(Base):
    """Immutable-price payment intent created from the server plan catalog."""

    __tablename__ = "billing_checkouts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_billing_checkouts_user_idempotency",
        ),
        Index("ix_billing_checkouts_user_created", "user_id", "created_at"),
        Index("ix_billing_checkouts_status_expires", "status", "expires_at"),
        Index(
            "uq_billing_checkouts_provider_order",
            "provider",
            "provider_order_id",
            unique=True,
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan = Column(String(20), nullable=False)
    months = Column(Integer, nullable=False, default=1)
    amount_minor = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="GEL")
    provider = Column(String(20), nullable=False, default="manual")
    status = Column(String(20), nullable=False, default="pending")
    idempotency_key = Column(String(128), nullable=False)
    provider_order_id = Column(String(255), nullable=True)
    provider_status = Column(String(40), nullable=True)
    provider_redirect_url = Column(String(1000), nullable=True)
    provider_checked_at = Column(DateTime, nullable=True)
    # Durable evidence of the exact public terms accepted before checkout.
    # These are nullable only so existing historical checkout rows remain valid.
    terms_version = Column(String(32), nullable=True)
    terms_accepted_at = Column(DateTime, nullable=True)
    immediate_service_requested_at = Column(DateTime, nullable=True)
    settled_payment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = relationship("User")
    settled_payment = relationship("Payment", foreign_keys=[settled_payment_id])


class BillingProviderEvent(Base):
    """Idempotent digest of one verified provider state transition."""

    __tablename__ = "billing_provider_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_billing_provider_event"),
        Index("ix_billing_provider_events_checkout_created", "checkout_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    checkout_id = Column(
        UUID(as_uuid=True),
        ForeignKey("billing_checkouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider = Column(String(20), nullable=False)
    event_id = Column(String(200), nullable=False)
    provider_status = Column(String(40), nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    processing_status = Column(String(20), nullable=False)
    error_code = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    checkout = relationship("BillingCheckout")
