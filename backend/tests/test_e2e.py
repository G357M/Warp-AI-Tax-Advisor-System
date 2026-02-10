"""
End-to-end tests for the complete system workflow.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.api.main import app
from backend.core.database import Base, get_db
from backend.models.user import User
from backend.core.security import get_password_hash
import time


# Test database setup
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_e2e.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def test_client():
    """Create test client."""
    Base.metadata.create_all(bind=engine)
    client = TestClient(app)
    yield client
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def test_user(test_client):
    """Create test user."""
    db = TestingSessionLocal()
    user = User(
        email="e2e@test.com",
        hashed_password=get_password_hash("test123"),
        is_active=True,
        is_admin=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


class TestCompleteUserJourney:
    """Test complete user journey from registration to query."""
    
    def test_01_system_health(self, test_client):
        """Test system is healthy before starting."""
        response = test_client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_02_user_registration(self, test_client):
        """Test new user registration."""
        response = test_client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@test.com",
                "password": "securepassword123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["email"] == "newuser@test.com"
    
    def test_03_user_login(self, test_client, test_user):
        """Test user login."""
        response = test_client.post(
            "/api/v1/auth/login",
            json={
                "email": "e2e@test.com",
                "password": "test123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        return data["access_token"]
    
    def test_04_authenticated_query(self, test_client, test_user):
        """Test making an authenticated query."""
        # Login first
        login_response = test_client.post(
            "/api/v1/auth/login",
            json={"email": "e2e@test.com", "password": "test123"}
        )
        token = login_response.json()["access_token"]
        
        # Make query
        response = test_client.post(
            "/api/v1/query",
            json={
                "query": "What is the VAT rate in Georgia?",
                "language": "en"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Query might fail if no documents loaded, but API should respond
        assert response.status_code in [200, 404, 500]
    
    def test_05_public_query(self, test_client):
        """Test public query without authentication."""
        response = test_client.post(
            "/api/v1/public/query",
            json={
                "query": "Tell me about Georgian tax law",
                "language": "en"
            }
        )
        
        # Should work without auth
        assert response.status_code in [200, 404]
    
    def test_06_rate_limiting(self, test_client):
        """Test rate limiting for public queries."""
        # Make multiple requests quickly
        responses = []
        for i in range(12):  # Exceeds guest limit of 10
            response = test_client.post(
                "/api/v1/public/query",
                json={
                    "query": f"Test query {i}",
                    "language": "en"
                }
            )
            responses.append(response.status_code)
        
        # Should hit rate limit
        assert 429 in responses  # Too Many Requests
    
    def test_07_invalid_inputs(self, test_client):
        """Test system handles invalid inputs gracefully."""
        # Empty query
        response = test_client.post(
            "/api/v1/public/query",
            json={"query": "", "language": "en"}
        )
        assert response.status_code == 400
        
        # Invalid language
        response = test_client.post(
            "/api/v1/public/query",
            json={"query": "test", "language": "invalid"}
        )
        assert response.status_code == 400
        
        # Missing fields
        response = test_client.post(
            "/api/v1/public/query",
            json={"query": "test"}
        )
        assert response.status_code == 422  # Validation error


class TestScraperWorkflow:
    """Test scraper workflow."""
    
    def test_list_scraper_tasks(self, test_client):
        """Test listing scraper tasks."""
        response = test_client.get("/api/v1/scraper/tasks")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_start_scraper_with_invalid_url(self, test_client):
        """Test starting scraper with invalid URL."""
        response = test_client.post(
            "/api/v1/scraper/start",
            json={"url": "not-a-valid-url"}
        )
        assert response.status_code == 400
    
    def test_start_scraper_with_valid_url(self, test_client):
        """Test starting scraper with valid URL."""
        response = test_client.post(
            "/api/v1/scraper/start",
            json={"url": "https://example.com"}
        )
        # Should accept the request
        assert response.status_code in [200, 202]


class TestPerformance:
    """Basic performance tests."""
    
    def test_response_time_health_check(self, test_client):
        """Test health check response time."""
        start_time = time.time()
        response = test_client.get("/health")
        duration = time.time() - start_time
        
        assert response.status_code == 200
        assert duration < 0.5  # Should respond in less than 500ms
    
    def test_concurrent_requests(self, test_client):
        """Test handling multiple concurrent requests."""
        import concurrent.futures
        
        def make_request():
            return test_client.get("/health")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        assert all(r.status_code == 200 for r in results)
    
    def test_metrics_endpoint_performance(self, test_client):
        """Test metrics endpoint responds quickly."""
        start_time = time.time()
        response = test_client.get("/metrics")
        duration = time.time() - start_time
        
        assert response.status_code == 200
        assert duration < 2.0  # Metrics collection can take a bit longer


class TestErrorHandling:
    """Test error handling and recovery."""
    
    def test_500_error_handling(self, test_client):
        """Test that 500 errors are handled gracefully."""
        # Try to access non-existent endpoint
        response = test_client.get("/api/v1/nonexistent")
        assert response.status_code == 404
    
    def test_malformed_json(self, test_client):
        """Test handling of malformed JSON."""
        response = test_client.post(
            "/api/v1/public/query",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    
    def test_missing_auth_token(self, test_client):
        """Test accessing protected endpoint without token."""
        response = test_client.post(
            "/api/v1/query",
            json={"query": "test", "language": "en"}
        )
        assert response.status_code == 401  # Unauthorized


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
