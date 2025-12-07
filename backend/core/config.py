"""
Application configuration settings.
"""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "InfoHub AI Tax Advisor"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=True, env="DEBUG")
    
    # API
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")
    API_PREFIX: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    
    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:80"],
        env="CORS_ORIGINS"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")
    
    # Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DB_POOL_SIZE: int = Field(default=20, env="DB_POOL_SIZE")
    DB_MAX_OVERFLOW: int = Field(default=10, env="DB_MAX_OVERFLOW")
    
    # Redis
    REDIS_URL: str = Field(..., env="REDIS_URL")
    CACHE_ENABLED: bool = Field(default=True, env="CACHE_ENABLED")
    CACHE_TTL_QUERY: int = Field(default=3600, env="CACHE_TTL_QUERY")
    CACHE_TTL_DOCUMENT: int = Field(default=7200, env="CACHE_TTL_DOCUMENT")
    
    # Vector Database
    VECTOR_DB_TYPE: str = Field(default="chromadb", env="VECTOR_DB_TYPE")
    CHROMA_HOST: str = Field(default="localhost", env="CHROMA_HOST")
    CHROMA_PORT: int = Field(default=8000, env="CHROMA_PORT")
    CHROMA_AUTH_TOKEN: Optional[str] = Field(default=None, env="CHROMA_AUTH_TOKEN")
    
    # AI/ML
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    LLM_PROVIDER: str = Field(default="openai", env="LLM_PROVIDER")
    LLM_MODEL: str = Field(default="gpt-4-turbo-preview", env="LLM_MODEL")
    LLM_TEMPERATURE: float = Field(default=0.3, env="LLM_TEMPERATURE")
    LLM_MAX_TOKENS: int = Field(default=2000, env="LLM_MAX_TOKENS")
    
    EMBEDDING_MODEL: str = Field(
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        env="EMBEDDING_MODEL"
    )
    EMBEDDING_DIMENSION: int = Field(default=768, env="EMBEDDING_DIMENSION")
    
    # RAG Configuration
    RAG_TOP_K: int = Field(default=10, env="RAG_TOP_K")
    RAG_RERANK_TOP_K: int = Field(default=5, env="RAG_RERANK_TOP_K")
    RAG_CHUNK_SIZE: int = Field(default=1024, env="RAG_CHUNK_SIZE")
    RAG_CHUNK_OVERLAP: int = Field(default=128, env="RAG_CHUNK_OVERLAP")
    RAG_MIN_SIMILARITY: float = Field(default=0.5, env="RAG_MIN_SIMILARITY")
    
    # Web Scraper
    SCRAPER_USER_AGENT: str = Field(
        default="InfoHubAI-Bot/1.0",
        env="SCRAPER_USER_AGENT"
    )
    SCRAPER_DELAY: float = Field(default=2.0, env="SCRAPER_DELAY")
    SCRAPER_CONCURRENT_REQUESTS: int = Field(default=5, env="SCRAPER_CONCURRENT_REQUESTS")
    SCRAPER_RESPECT_ROBOTS_TXT: bool = Field(default=True, env="SCRAPER_RESPECT_ROBOTS_TXT")
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_GUEST: str = Field(default="10/minute", env="RATE_LIMIT_GUEST")
    RATE_LIMIT_USER: str = Field(default="60/minute", env="RATE_LIMIT_USER")
    RATE_LIMIT_ADMIN: str = Field(default="1000/minute", env="RATE_LIMIT_ADMIN")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = Field(default="json", env="LOG_FORMAT")
    LOG_FILE_PATH: str = Field(default="logs/app.log", env="LOG_FILE_PATH")
    
    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    CELERY_TASK_TIME_LIMIT: int = Field(default=3600, env="CELERY_TASK_TIME_LIMIT")
    
    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("LLM_PROVIDER")
    def validate_llm_provider(cls, v):
        """Validate LLM provider."""
        allowed = ["openai", "anthropic"]
        if v not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
