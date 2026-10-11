"""Read-only, whitelisted view of runtime configuration for the admin panel."""
from pydantic import SecretStr

from core.config import settings
from core.plans import FREE_DAILY_QUESTIONS

PUBLIC_CONFIG = {
    "app": ("APP_VERSION", "ENVIRONMENT", "DEBUG"),
    "llm": ("LLM_PROVIDER", "LLM_MODEL", "EMBEDDING_MODEL", "RAG_TOP_K", "RAG_MIN_SIMILARITY", "JEV_MODE"),
    "email": ("EMAIL_DELIVERY_ENABLED", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM"),
    "billing": ("BILLING_TBC_ENABLED", "BILLING_CONTACT_EMAIL"),
    "limits": ("RATE_LIMIT_ENABLED",),
}
SECRET_PRESENCE = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "SMTP_PASSWORD", "TBC_API_KEY",
    "TBC_CLIENT_ID", "TBC_CLIENT_SECRET", "TYPESAFE_API_KEY",
)


def _is_set(value) -> bool:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return bool(value.strip()) if isinstance(value, str) else value is not None


def public_config(source=settings) -> dict:
    groups = {group: {name: getattr(source, name) for name in names} for group, names in PUBLIC_CONFIG.items()}
    groups["billing"]["FREE_DAILY_QUESTIONS"] = FREE_DAILY_QUESTIONS
    groups["secrets"] = {name: _is_set(getattr(source, name, None)) for name in SECRET_PRESENCE}
    return groups
