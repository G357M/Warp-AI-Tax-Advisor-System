"""Application configuration settings."""

import json
from typing import Any, Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "InfoHub AI Tax Advisor"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str
    JWT_SECRET_KEY: str
    JWT_PREVIOUS_SECRET_KEYS: str = ""
    JWT_PREVIOUS_SECRET_ACCEPT_UNTIL: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    # The str branch keeps comma-separated values compatible with
    # pydantic-settings 2.1; the validator always normalizes it to a list.
    CORS_ORIGINS: list[str] | str = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:80"]
    )
    CORS_ALLOW_CREDENTIALS: bool = True

    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str
    CACHE_ENABLED: bool = True
    CACHE_TTL_QUERY: int = 3600
    CACHE_TTL_DOCUMENT: int = 7200

    # Vector Database
    VECTOR_DB_TYPE: str = "pgvector"
    CHROMA_HOST: Optional[str] = None
    CHROMA_PORT: Optional[int] = None
    CHROMA_AUTH_TOKEN: Optional[str] = None

    # AI/ML
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2000

    EMBEDDING_MODEL: str = (
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    )
    EMBEDDING_DIMENSION: int = 768

    # RAG Configuration
    RAG_TOP_K: int = 10
    RAG_RERANK_TOP_K: int = 5
    RAG_CHUNK_SIZE: int = 1024
    RAG_CHUNK_OVERLAP: int = 128
    RAG_MIN_SIMILARITY: float = 0.5

    # Web Scraper
    SCRAPER_USER_AGENT: str = "InfoHubAI-Bot/1.0"
    SCRAPER_DELAY: float = 2.0
    SCRAPER_CONCURRENT_REQUESTS: int = 5
    SCRAPER_RESPECT_ROBOTS_TXT: bool = True

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_GUEST: str = "10/minute"
    RATE_LIMIT_USER: str = "60/minute"
    RATE_LIMIT_ADMIN: str = "1000/minute"
    RATE_LIMIT_BYPASS_TOKEN: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE_PATH: str = "logs/app.log"

    # Celery. Explicit Celery variables win; REDIS_URL remains the fallback.
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CELERY_BROKER_URL", "REDIS_URL"),
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND", "REDIS_URL"),
    )
    CELERY_TASK_TIME_LIMIT: int = 3600

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        """Accept both JSON arrays and the documented comma-separated form."""
        if not isinstance(value, str):
            return value

        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            decoded = json.loads(raw)
            if not isinstance(decoded, list):
                raise ValueError("CORS_ORIGINS JSON value must be an array")
            return decoded
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @field_validator("LLM_PROVIDER")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        """Validate LLM provider."""
        allowed = ["openai", "anthropic"]
        if value not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}")
        return value

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret_key(cls, value: str) -> str:
        """HS256 requires at least 256 bits of key material."""
        if len(value.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 UTF-8 bytes")
        return value


# Global settings instance
settings = Settings()
