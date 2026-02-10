"""
Load testing script using Locust.

Usage:
    locust -f backend/tests/load_test.py --host=http://localhost:8000

Or run headless:
    locust -f backend/tests/load_test.py --host=http://localhost:8000 --users 100 --spawn-rate 10 --run-time 1m --headless
"""
from locust import HttpUser, task, between, TaskSet
import random
import json


class QueryBehavior(TaskSet):
    """User behavior for making queries."""
    
    queries = [
        "What is the VAT rate in Georgia?",
        "How to register a company in Georgia?",
        "Tell me about corporate tax",
        "What are the income tax rates?",
        "How to file tax returns?",
        "What is the deadline for tax payment?",
        "Are there any tax exemptions?",
        "How to get tax ID in Georgia?",
    ]
    
    languages = ["en", "ru", "ka"]
    
    @task(10)
    def public_query(self):
        """Make a public query (most common action)."""
        query = random.choice(self.queries)
        language = random.choice(self.languages)
        
        self.client.post(
            "/api/v1/public/query",
            json={
                "query": query,
                "language": language
            },
            name="/api/v1/public/query"
        )
    
    @task(2)
    def health_check(self):
        """Check system health."""
        self.client.get("/health", name="/health")
    
    @task(1)
    def get_metrics(self):
        """Get metrics (less frequent)."""
        self.client.get("/metrics", name="/metrics")


class AuthenticatedUserBehavior(TaskSet):
    """Behavior for authenticated users."""
    
    def on_start(self):
        """Login when user starts."""
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword"
            }
        )
        
        if response.status_code == 200:
            self.token = response.json().get("access_token")
        else:
            # If login fails, register
            response = self.client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"user{random.randint(1000,9999)}@test.com",
                    "password": "testpassword"
                }
            )
            if response.status_code == 200:
                self.token = response.json().get("access_token")
            else:
                self.token = None
    
    @task(10)
    def authenticated_query(self):
        """Make an authenticated query."""
        if not self.token:
            return
        
        query = random.choice([
            "What is the VAT rate?",
            "How to register company?",
            "Tell me about taxes",
        ])
        
        self.client.post(
            "/api/v1/query",
            json={
                "query": query,
                "language": "en"
            },
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/v1/query (auth)"
        )
    
    @task(1)
    def get_profile(self):
        """Get user profile."""
        if not self.token:
            return
        
        self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/v1/auth/me"
        )


class GuestUser(HttpUser):
    """Simulates guest users (no authentication)."""
    tasks = [QueryBehavior]
    wait_time = between(1, 5)  # Wait 1-5 seconds between tasks
    weight = 7  # 70% of users are guests


class RegisteredUser(HttpUser):
    """Simulates registered users (with authentication)."""
    tasks = [AuthenticatedUserBehavior]
    wait_time = between(2, 6)
    weight = 3  # 30% of users are registered


class StressTest(HttpUser):
    """Stress test with rapid requests."""
    wait_time = between(0.1, 0.5)  # Very short wait
    
    @task
    def rapid_health_checks(self):
        """Make rapid health check requests."""
        self.client.get("/health")


class SpikeBehavior(TaskSet):
    """Simulates spike traffic."""
    
    @task
    def burst_queries(self):
        """Send burst of queries."""
        for _ in range(5):
            self.client.post(
                "/api/v1/public/query",
                json={
                    "query": "Test query",
                    "language": "en"
                },
                name="/api/v1/public/query (burst)"
            )


# Performance benchmarks
class PerformanceBenchmark(HttpUser):
    """Benchmark critical endpoints."""
    wait_time = between(1, 2)
    
    @task(5)
    def benchmark_public_query(self):
        """Benchmark public query endpoint."""
        self.client.post(
            "/api/v1/public/query",
            json={
                "query": "What is the VAT rate?",
                "language": "en"
            }
        )
    
    @task(3)
    def benchmark_health(self):
        """Benchmark health endpoint."""
        self.client.get("/health")
    
    @task(1)
    def benchmark_metrics(self):
        """Benchmark metrics endpoint."""
        self.client.get("/metrics")
    
    @task(1)
    def benchmark_scraper_list(self):
        """Benchmark scraper list endpoint."""
        self.client.get("/api/v1/scraper/tasks")


if __name__ == "__main__":
    import os
    os.system("locust -f load_test.py --host=http://localhost:8000")
