"""The payment reconciliation worklist predicate, shared by the list and its counters."""
from sqlalchemy import and_, or_

from core.time_utils import utc_now
from models import BillingCheckout


def reconciliation_queue_filter():
    """Checkouts an operator must inspect, including TBC orders whose final callback never arrived."""
    return or_(
        BillingCheckout.status.in_(("provider_unknown", "provider_review")),
        and_(
            BillingCheckout.provider == "tbc",
            BillingCheckout.status.in_(("pending", "expired")),
            BillingCheckout.settled_payment_id.is_(None),
            BillingCheckout.expires_at < utc_now(),
            or_(
                BillingCheckout.provider_status.is_(None),
                BillingCheckout.provider_status.notin_(("Failed", "Expired")),
            ),
        ),
    )
