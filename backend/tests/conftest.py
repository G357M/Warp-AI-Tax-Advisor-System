"""Pytest configuration."""
import os

# Set default environment variables for tests
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-minimum-32-characters")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-for-tests-minimum-32")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
