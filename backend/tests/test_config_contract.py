"""Regression tests for environment-backed application settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import Settings
from rag_v2.adapters import load_backend_config


REQUIRED_ENV = {
    "SECRET_KEY": "test-application-secret-with-at-least-32-characters",
    "JWT_SECRET_KEY": "test-jwt-secret-with-at-least-32-characters",
    "DATABASE_URL": "sqlite:///test.db",
    "REDIS_URL": "redis://redis:6379/15",
}


def _set_required_env(monkeypatch) -> None:
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)


def test_cors_origins_accept_production_json(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", '["https://tax-advisor.ge"]')

    settings = Settings(_env_file=None)

    assert settings.CORS_ORIGINS == ["https://tax-advisor.ge"]


def test_cors_origins_accept_documented_comma_separated_form(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000, http://localhost:80",
    )

    settings = Settings(_env_file=None)

    assert settings.CORS_ORIGINS == [
        "http://localhost:3000",
        "http://localhost:80",
    ]


def test_celery_defaults_to_the_configured_redis_service(monkeypatch):
    _set_required_env(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.CELERY_BROKER_URL == REQUIRED_ENV["REDIS_URL"]
    assert settings.CELERY_RESULT_BACKEND == REQUIRED_ENV["REDIS_URL"]


def test_explicit_celery_urls_override_redis_fallback(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://broker:6379/1")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://results:6379/2")

    settings = Settings(_env_file=None)

    assert settings.CELERY_BROKER_URL == "redis://broker:6379/1"
    assert settings.CELERY_RESULT_BACKEND == "redis://results:6379/2"


def test_embedding_download_policy_can_be_disabled(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("EMBEDDING_ALLOW_DOWNLOAD", "false")

    settings = Settings(_env_file=None)

    assert settings.EMBEDDING_ALLOW_DOWNLOAD is False


def test_billing_checkout_ttl_has_a_bounded_configuration(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BILLING_MANUAL_CHECKOUT_TTL_HOURS", "72")

    settings = Settings(_env_file=None)

    assert settings.BILLING_MANUAL_CHECKOUT_TTL_HOURS == 72


def test_tbc_checkout_cannot_be_enabled_with_partial_credentials(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BILLING_TBC_ENABLED", "true")
    monkeypatch.setenv("TBC_API_KEY", "api-key")
    monkeypatch.delenv("TBC_CLIENT_ID", raising=False)
    monkeypatch.delenv("TBC_CLIENT_SECRET", raising=False)

    with pytest.raises(ValidationError, match="TBC_CLIENT_ID"):
        Settings(_env_file=None)


def test_tbc_checkout_accepts_complete_https_configuration(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BILLING_TBC_ENABLED", "true")
    monkeypatch.setenv("TBC_API_KEY", "api-key")
    monkeypatch.setenv("TBC_CLIENT_ID", "merchant-id")
    monkeypatch.setenv("TBC_CLIENT_SECRET", "merchant-secret")
    monkeypatch.setenv("TBC_API_BASE_URL", "https://api.tbcbank.ge")
    monkeypatch.setenv("TBC_RETURN_URL", "https://tax-advisor.ge/account?payment_return=tbc")
    monkeypatch.setenv(
        "TBC_CALLBACK_URL",
        "https://tax-advisor.ge/api/v1/billing/providers/tbc/callback",
    )

    configured = Settings(_env_file=None)

    assert configured.BILLING_TBC_ENABLED is True
    assert configured.TBC_CLIENT_SECRET is not None
    assert configured.TBC_CLIENT_SECRET.get_secret_value() == "merchant-secret"


def test_production_tbc_rejects_an_untrusted_api_origin(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BILLING_TBC_ENABLED", "true")
    monkeypatch.setenv("TBC_API_KEY", "api-key")
    monkeypatch.setenv("TBC_CLIENT_ID", "merchant-id")
    monkeypatch.setenv("TBC_CLIENT_SECRET", "merchant-secret")
    monkeypatch.setenv("TBC_API_BASE_URL", "https://payments.example.com")

    with pytest.raises(ValidationError, match="api.tbcbank.ge"):
        Settings(_env_file=None)


def test_production_tbc_rejects_a_non_origin_api_base(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BILLING_TBC_ENABLED", "true")
    monkeypatch.setenv("TBC_API_KEY", "api-key")
    monkeypatch.setenv("TBC_CLIENT_ID", "merchant-id")
    monkeypatch.setenv("TBC_CLIENT_SECRET", "merchant-secret")
    monkeypatch.setenv("TBC_API_BASE_URL", "https://api.tbcbank.ge/untrusted-prefix")

    with pytest.raises(ValidationError, match="clean HTTPS origin"):
        Settings(_env_file=None)


def test_env_file_ignores_unrelated_legacy_entries(monkeypatch):
    for name in (*REQUIRED_ENV, "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    env_file = Path(__file__).parent / "fixtures" / "config_compat.env"

    settings = Settings(_env_file=env_file)

    assert settings.CORS_ORIGINS == [
        "https://tax-advisor.ge",
        "https://www.tax-advisor.ge",
    ]


def test_rag_db_adapter_has_no_embedded_connection_fallback(monkeypatch):
    monkeypatch.delenv("INFOHUB_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    config = load_backend_config()

    assert config.database_url is None
    assert config.mode == "fixtures"
