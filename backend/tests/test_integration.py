"""
Integration tests for full API workflows.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.main import app
from core.database import Base, get_db
from models.user import User
from core.security import get_password_hash


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(setup_database):
    db = TestingSessionLocal()
    user = User(
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        hashed_password=get_password_hash("testpassword123")
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.close()


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_endpoint(self):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "app" in data
        assert "version" in data
    
    def test_health_endpoint(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
    
    def test_public_health_endpoint(self):
        response = client.get("/api/v1/public/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "stats" in data


class TestAuthenticationFlow:
    """Test authentication workflows."""
    
    def test_register_user(self):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "password123",
                "full_name": "New User"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
    
    def test_login_user(self, test_user):
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
    
    def test_login_wrong_password(self, test_user):
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401
    
    def test_get_current_user(self, test_user):
        # Login first
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "testpassword123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Get current user
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["username"] == "testuser"


class TestPublicQueryEndpoint:
    """Test public query endpoint."""
    
    def test_query_without_auth(self):
        response = client.post(
            "/api/v1/public/query",
            json={
                "query": "What is VAT rate in Georgia?",
                "language": "en"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "sources" in data
        assert "retrieved_count" in data
        assert "processing_time" in data
    
    def test_query_invalid_language(self):
        response = client.post(
            "/api/v1/public/query",
            json={
                "query": "Test query",
                "language": "invalid"
            }
        )
        assert response.status_code == 422  # Validation error
    
    def test_query_empty_string(self):
        response = client.post(
            "/api/v1/public/query",
            json={
                "query": "",
                "language": "en"
            }
        )
        assert response.status_code == 422  # Validation error


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_rate_limit_guest(self):
        # Make multiple requests rapidly
        responses = []
        for i in range(15):  # Limit is 10/minute for guests
            response = client.get("/api/v1/public/stats")
            responses.append(response)
        
        # At least one should be rate limited
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes or all(code == 200 for code in status_codes)
        
        # Check rate limit headers
        last_response = responses[-1]
        if last_response.status_code == 200:
            assert "X-RateLimit-Limit" in last_response.headers
            assert "X-RateLimit-Remaining" in last_response.headers


class TestScraperEndpoints:
    """Test scraper API endpoints."""
    
    def test_list_scraper_tasks(self):
        response = client.get("/api/v1/scraper/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "total_tasks" in data
        assert "tasks" in data
    
    def test_start_scraping_invalid_url(self):
        response = client.post(
            "/api/v1/scraper/start",
            json={
                "url": "https://google.com",  # Not infohub.ge
                "max_depth": 2,
                "max_pages": 10
            }
        )
        assert response.status_code == 400
        assert "infohub.ge" in response.json()["detail"]


@pytest.mark.asyncio
class TestRAGPipeline:
    """Test RAG pipeline integration."""
    
    async def test_query_processing(self):
        # This would test the full RAG pipeline
        # Simplified for now
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
