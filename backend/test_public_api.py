"""
Test script for public API endpoints.
"""
import requests
import json


BASE_URL = "http://localhost:8000/api/v1"


def test_health_check():
    """Test public health check endpoint."""
    print("\n" + "=" * 60)
    print("Testing: GET /public/health")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/public/health")
    print(f"Status Code: {response.status_code}")
    print(f"Response:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("✅ Health check passed!")


def test_public_stats():
    """Test public stats endpoint."""
    print("\n" + "=" * 60)
    print("Testing: GET /public/stats")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/public/stats")
    print(f"Status Code: {response.status_code}")
    print(f"Response:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    assert response.status_code == 200
    data = response.json()
    assert "app_name" in data
    assert "supported_languages" in data
    print("✅ Stats endpoint passed!")


def test_public_query():
    """Test public query endpoint."""
    print("\n" + "=" * 60)
    print("Testing: POST /public/query")
    print("=" * 60)
    
    query_data = {
        "query": "Какой размер НДС в Грузии?",
        "language": "ru"
    }
    
    print(f"Request Body:\n{json.dumps(query_data, indent=2, ensure_ascii=False)}")
    
    response = requests.post(
        f"{BASE_URL}/public/query",
        json=query_data,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nResponse:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
        
        assert "response" in data
        assert "sources" in data
        assert "retrieved_count" in data
        assert "processing_time" in data
        print("\n✅ Public query endpoint passed!")
    else:
        print(f"\n❌ Error: {response.text}")


def test_root_endpoint():
    """Test root endpoint."""
    print("\n" + "=" * 60)
    print("Testing: GET /")
    print("=" * 60)
    
    response = requests.get("http://localhost:8000/")
    print(f"Status Code: {response.status_code}")
    print(f"Response:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    print("✅ Root endpoint passed!")


def main():
    """Run all tests."""
    print("\n" + "🚀" * 30)
    print("Starting Public API Tests")
    print("🚀" * 30)
    
    try:
        test_root_endpoint()
        test_health_check()
        test_public_stats()
        test_public_query()
        
        print("\n" + "✅" * 30)
        print("All tests passed successfully!")
        print("✅" * 30 + "\n")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Cannot connect to server at http://localhost:8000")
        print("Make sure the backend server is running!")
        print("Run: cd C:\\New_Projects\\Warp\\Warp_INFOHUB.GE && .\\backend\\venv\\Scripts\\Activate.ps1 && python -m backend.api.main")
        
    except AssertionError as e:
        print(f"\n❌ Test assertion failed: {e}")
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()
