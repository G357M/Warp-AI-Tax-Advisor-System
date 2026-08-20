"""Regression tests for environment-backed application settings."""

from pathlib import Path

from core.config import Settings


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


def test_env_file_ignores_unrelated_legacy_entries(monkeypatch):
    for name in (*REQUIRED_ENV, "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    env_file = Path(__file__).parent / "fixtures" / "config_compat.env"

    settings = Settings(_env_file=env_file)

    assert settings.CORS_ORIGINS == [
        "https://tax-advisor.ge",
        "https://www.tax-advisor.ge",
    ]
