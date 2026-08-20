"""
Payment gateways behind one interface.

ManualGateway works from day one: checkout returns payment instructions and an
admin activates the subscription after an invoice/transfer. BogIPayGateway is
the Bank of Georgia e-commerce slot — it activates automatically once merchant
credentials appear in the environment (BOG_CLIENT_ID / BOG_CLIENT_SECRET).
"""
import os
from typing import Any, Dict

PLAN_PRICES_GEL = {"pro": 49.0, "business": 149.0}
CHECKOUT_CONTACT_EMAIL = "ggrishikashvili@gmail.com"


class ManualGateway:
    name = "manual"

    def create_checkout(self, user, plan: str) -> Dict[str, Any]:
        price = PLAN_PRICES_GEL[plan]
        return {
            "provider": self.name,
            "plan": plan,
            "amount_gel": price,
            "contact_email": CHECKOUT_CONTACT_EMAIL,
            "instructions": (
                f"Тариф {plan.capitalize()} — {price:g} ₾/мес. Онлайн-оплата скоро подключится; "
                f"пока напишите нам на {CHECKOUT_CONTACT_EMAIL} — выставим счёт и активируем "
                "подписку вручную в течение рабочего дня."
            ),
        }


class BogIPayGateway:
    name = "bog"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    def create_checkout(self, user, plan: str) -> Dict[str, Any]:
        # Wire the BOG iPay order-creation call here once merchant onboarding
        # completes; until then the manual flow serves checkouts.
        raise NotImplementedError("BOG iPay checkout is not wired yet")


def get_gateway():
    client_id = os.getenv("BOG_CLIENT_ID", "").strip()
    client_secret = os.getenv("BOG_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return BogIPayGateway(client_id, client_secret)
    return ManualGateway()
