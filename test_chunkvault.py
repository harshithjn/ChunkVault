"""
Comprehensive test suite for ChunkVault
"""
import pytest
import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import app, Base, get_db, get_current_user
from cache import CacheManager
import redis

# Test configuration
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_chunkvault.db")
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")

@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine"""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="session")
def test_session(test_engine):
    """Create test database session"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture(scope="session")
def test_redis():
    """Create test Redis client"""
    redis_client = redis.from_url(TEST_REDIS_URL)
    yield redis_client
    redis_client.flushdb()

@pytest.fixture(scope="session")
def test_cache(test_redis):
    """Create test cache manager"""
    return CacheManager()

@pytest.fixture(scope="session")
def client(test_engine):
    """Create test client"""
    def override_get_db():
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

@pytest.fixture(scope="session")
def auth_headers(client):
    """Get authentication headers for testing"""
    # Register test user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword"
    }
    response = client.post("/auth/register", json=user_data)
    assert response.status_code == 200
    
    # Login and get token
    login_data = {
        "username": "testuser",
        "password": "testpassword"
    }
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}

class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_register_user(self, client):
        """Test user registration"""
        user_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newpassword"
        }
        response = client.post("/auth/register", json=user_data)
        assert response.status_code == 200
        assert "user_id" in response.json()
    
    def test_register_duplicate_user(self, client):
        """Test duplicate user registration"""
        user_data = {
            "username": "duplicate",
            "email": "duplicate@example.com",
            "password": "password"
        }
        # First registration
        response = client.post("/auth/register", json=user_data)
        assert response.status_code == 200
        
        # Second registration should fail
        response = client.post("/auth/register", json=user_data)
        assert response.status_code == 400
    
    def test_login_valid_user(self, client):
        """Test valid user login"""
        # Register user first
        user_data = {
            "username": "loginuser",
            "email": "loginuser@example.com",
            "password": "loginpassword"
        }
        client.post("/auth/register", json=user_data)
        
        # Login
        login_data = {
            "username": "loginuser",
            "password": "loginpassword"
        }
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 200
        assert "access_token" in response.json()
    
    def test_login_invalid_user(self, client):
        """Test invalid user login"""
        login_data = {
            "username": "nonexistent",
            "password": "wrongpassword"
        }
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 401

class TestFileOperations:
    """Test file upload, download, and management"""
    
    def test_upload_file(self, client, auth_headers):
        """Test file upload"""
        # Create a test file
        test_content = b"Hello, ChunkVault! This is a test file."
        files = {"file": ("test.txt", test_content, "text/plain")}
        
        response = client.post("/files/upload", files=files, headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "file_id" in data
        assert data["filename"] == "test.txt"
        assert data["size"] == len(test_content)
    
    def test_list_files(self, client, auth_headers):
        """Test file listing"""
        response = client.get("/files", headers=auth_headers)
        assert response.status_code == 200
        
        files = response.json()
        assert isinstance(files, list)
    
    def test_download_file(self, client, auth_headers):
        """Test file download"""
        # Upload a file first
        test_content = b"Download test content"
        files = {"file": ("download_test.txt", test_content, "text/plain")}
        upload_response = client.post("/files/upload", files=files, headers=auth_headers)
        file_id = upload_response.json()["file_id"]
        
        # Download the file
        response = client.get(f"/files/{file_id}/download", headers=auth_headers)
        assert response.status_code == 200
        assert response.content == test_content
    
    def test_create_share_link(self, client, auth_headers):
        """Test share link creation"""
        # Upload a file first
        test_content = b"Share test content"
        files = {"file": ("share_test.txt", test_content, "text/plain")}
        upload_response = client.post("/files/upload", files=files, headers=auth_headers)
        file_id = upload_response.json()["file_id"]
        
        # Create share link
        share_data = {"expires_in_hours": 24}
        response = client.post(f"/files/{file_id}/share", json=share_data, headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "share_token" in data
        assert "share_url" in data
    
    def test_download_shared_file(self, client, auth_headers):
        """Test downloading shared file"""
        # Upload a file first
        test_content = b"Shared file content"
        files = {"file": ("shared_test.txt", test_content, "text/plain")}
        upload_response = client.post("/files/upload", files=files, headers=auth_headers)
        file_id = upload_response.json()["file_id"]
        
        # Create share link
        share_data = {"expires_in_hours": 24}
        share_response = client.post(f"/files/{file_id}/share", json=share_data, headers=auth_headers)
        share_token = share_response.json()["share_token"]
        
        # Download shared file
        response = client.get(f"/share/{share_token}")
        assert response.status_code == 200
        assert response.content == test_content

class TestCache:
    """Test Redis caching functionality"""
    
    def test_cache_set_get(self, test_cache):
        """Test basic cache operations"""
        key = "test_key"
        value = {"test": "data", "number": 123}
        
        # Set value
        assert test_cache.set(key, value) == True
        
        # Get value
        retrieved = test_cache.get(key)
        assert retrieved == value
    
    def test_cache_expiration(self, test_cache):
        """Test cache expiration"""
        key = "expire_test"
        value = "expire_value"
        
        # Set with short expiration
        assert test_cache.set(key, value, expire=1) == True
        
        # Should be available immediately
        assert test_cache.get(key) == value
        
        # Wait for expiration
        import time
        time.sleep(2)
        
        # Should be None after expiration
        assert test_cache.get(key) is None
    
    def test_cache_user_files(self, test_cache):
        """Test user files caching"""
        user_id = "test_user_123"
        files = [
            {"id": "file1", "name": "test1.txt"},
            {"id": "file2", "name": "test2.txt"}
        ]
        
        # Set user files
        assert test_cache.set_user_files(user_id, files) == True
        
        # Get user files
        retrieved = test_cache.get_user_files(user_id)
        assert retrieved == files
        
        # Invalidate cache
        assert test_cache.invalidate_user_files(user_id) == True
        assert test_cache.get_user_files(user_id) is None

class TestHealthChecks:
    """Test health check endpoints"""
    
    def test_api_health(self, client):
        """Test API health check"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "chunkvault"
    
    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert data["message"] == "ChunkVault API"
        assert data["version"] == "1.0.0"

class TestMetrics:
    """Test Prometheus metrics"""
    
    def test_metrics_endpoint(self, client):
        """Test metrics endpoint"""
        response = client.get("/metrics")
        assert response.status_code == 200
        
        # Check for some expected metrics
        content = response.text
        assert "chunkvault_requests_total" in content
        assert "chunkvault_request_duration_seconds" in content

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
