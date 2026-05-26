"""
Comprehensive test suite for ChunkVault (Flask implementation)
"""
import pytest
import os
import tempfile
import shutil
import io
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app as app_module
from app import app, Base
from Scripts.cache import CacheManager
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
    try:
        redis_client = redis.from_url(TEST_REDIS_URL)
        yield redis_client
        redis_client.flushdb()
    except Exception:
        pytest.skip("Redis server offline. Skipping Redis-dependent tests.")

@pytest.fixture(scope="session")
def test_cache(test_redis):
    """Create test cache manager"""
    return CacheManager()

@pytest.fixture(scope="session")
def client(test_engine):
    """Create test client and override app SessionLocal with test engine"""
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Monkey-patch SessionLocal globally
    original_session_local = app_module.SessionLocal
    app_module.SessionLocal = TestSessionLocal
    
    # Configure Flask app for testing
    app.config["TESTING"] = True
    
    with app.test_client() as client:
        yield client
        
    # Restore original SessionLocal
    app_module.SessionLocal = original_session_local

@pytest.fixture(scope="session")
def auth_headers(client):
    """Get authentication headers for testing"""
    # Register test user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword"
    }
    response = client.post("/api/auth/register", json=user_data)
    assert response.status_code == 200
    
    # Login and get token
    login_data = {
        "username": "testuser",
        "password": "testpassword"
    }
    response = client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200
    token = response.get_json()["access_token"]
    
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
        response = client.post("/api/auth/register", json=user_data)
        assert response.status_code == 200
        assert "user_id" in response.get_json()
    
    def test_register_duplicate_user(self, client):
        """Test duplicate user registration"""
        user_data = {
            "username": "duplicate",
            "email": "duplicate@example.com",
            "password": "password"
        }
        # First registration
        response = client.post("/api/auth/register", json=user_data)
        assert response.status_code == 200
        
        # Second registration should fail
        response = client.post("/api/auth/register", json=user_data)
        assert response.status_code == 400
    
    def test_login_valid_user(self, client):
        """Test valid user login"""
        # Register user first
        user_data = {
            "username": "loginuser",
            "email": "loginuser@example.com",
            "password": "loginpassword"
        }
        client.post("/api/auth/register", json=user_data)
        
        # Login
        login_data = {
            "username": "loginuser",
            "password": "loginpassword"
        }
        response = client.post("/api/auth/login", json=login_data)
        assert response.status_code == 200
        assert "access_token" in response.get_json()
    
    def test_login_invalid_user(self, client):
        """Test invalid user login"""
        login_data = {
            "username": "nonexistent",
            "password": "wrongpassword"
        }
        response = client.post("/api/auth/login", json=login_data)
        assert response.status_code == 401

class TestFileOperations:
    """Test file upload, download, and management"""
    
    def test_upload_file(self, client, auth_headers):
        """Test file upload"""
        test_content = b"Hello, ChunkVault! This is a test file."
        
        # In Flask test client, upload is sent under the data dict using file tuple
        data = {
            "file": (io.BytesIO(test_content), "test.txt")
        }
        
        # Mock synchronous node chunk storing to make tests fully decoupled
        def mock_store(*args, **kwargs):
            return True
            
        original_store = app_module.store_chunk_to_nodes_sync
        app_module.store_chunk_to_nodes_sync = mock_store
        
        try:
            response = client.post("/api/files/upload", data=data, headers=auth_headers)
            assert response.status_code == 200
            
            res_data = response.get_json()
            assert "file_id" in res_data
            assert res_data["filename"] == "test.txt"
            assert res_data["size"] == len(test_content)
        finally:
            app_module.store_chunk_to_nodes_sync = original_store
    
    def test_list_files(self, client, auth_headers):
        """Test file listing"""
        response = client.get("/api/files", headers=auth_headers)
        assert response.status_code == 200
        
        files = response.get_json()
        assert isinstance(files, list)
    
    def test_download_file(self, client, auth_headers):
        """Test file download"""
        test_content = b"Download test content"
        data = {
            "file": (io.BytesIO(test_content), "download_test.txt")
        }
        
        # Mock storing and retrieving chunks from nodes to run without live storage node servers
        def mock_store(*args, **kwargs): return True
        def mock_retrieve(*args, **kwargs): return test_content
        
        original_store = app_module.store_chunk_to_nodes_sync
        original_retrieve = app_module.retrieve_chunk_from_nodes_sync
        
        app_module.store_chunk_to_nodes_sync = mock_store
        app_module.retrieve_chunk_from_nodes_sync = mock_retrieve
        
        try:
            upload_response = client.post("/api/files/upload", data=data, headers=auth_headers)
            file_id = upload_response.get_json()["file_id"]
            
            # Download file
            response = client.get(f"/api/files/{file_id}/download", headers=auth_headers)
            assert response.status_code == 200
            assert response.data == test_content
        finally:
            app_module.store_chunk_to_nodes_sync = original_store
            app_module.retrieve_chunk_from_nodes_sync = original_retrieve
    
    def test_create_share_link(self, client, auth_headers):
        """Test share link creation"""
        test_content = b"Share test content"
        data = {
            "file": (io.BytesIO(test_content), "share_test.txt")
        }
        
        def mock_store(*args, **kwargs): return True
        original_store = app_module.store_chunk_to_nodes_sync
        app_module.store_chunk_to_nodes_sync = mock_store
        
        try:
            upload_response = client.post("/api/files/upload", data=data, headers=auth_headers)
            file_id = upload_response.get_json()["file_id"]
            
            # Share link
            share_data = {"expires_in_hours": 24}
            response = client.post(f"/api/files/{file_id}/share", json=share_data, headers=auth_headers)
            assert response.status_code == 200
            
            res_data = response.get_json()
            assert "share_token" in res_data
            assert "share_url" in res_data
        finally:
            app_module.store_chunk_to_nodes_sync = original_store
    
    def test_download_shared_file(self, client, auth_headers):
        """Test downloading shared file"""
        test_content = b"Shared file content"
        data = {
            "file": (io.BytesIO(test_content), "shared_test.txt")
        }
        
        def mock_store(*args, **kwargs): return True
        def mock_retrieve(*args, **kwargs): return test_content
        
        original_store = app_module.store_chunk_to_nodes_sync
        original_retrieve = app_module.retrieve_chunk_from_nodes_sync
        
        app_module.store_chunk_to_nodes_sync = mock_store
        app_module.retrieve_chunk_from_nodes_sync = mock_retrieve
        
        try:
            upload_response = client.post("/api/files/upload", data=data, headers=auth_headers)
            file_id = upload_response.get_json()["file_id"]
            
            # Create share token
            share_data = {"expires_in_hours": 24}
            share_response = client.post(f"/api/files/{file_id}/share", json=share_data, headers=auth_headers)
            share_token = share_response.get_json()["share_token"]
            
            # Download shared file
            response = client.get(f"/api/share/{share_token}/download")
            assert response.status_code == 200
            assert response.data == test_content
        finally:
            app_module.store_chunk_to_nodes_sync = original_store
            app_module.retrieve_chunk_from_nodes_sync = original_retrieve

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
        
        assert test_cache.set(key, value, expire=1) == True
        assert test_cache.get(key) == value
        
        import time
        time.sleep(2)
        assert test_cache.get(key) is None
    
    def test_cache_user_files(self, test_cache):
        """Test user files caching"""
        user_id = "test_user_123"
        files = [
            {"id": "file1", "name": "test1.txt"},
            {"id": "file2", "name": "test2.txt"}
        ]
        
        assert test_cache.set_user_files(user_id, files) == True
        retrieved = test_cache.get_user_files(user_id)
        assert retrieved == files
        
        assert test_cache.invalidate_user_files(user_id) == True
        assert test_cache.get_user_files(user_id) is None

class TestHealthChecks:
    """Test health check endpoints"""
    
    def test_api_health(self, client):
        """Test API health check"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["service"] == "chunkvault"
    
    def test_root_endpoint(self, client):
        """Test root endpoint serves HTML dashboard page"""
        response = client.get("/")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data

class TestMetrics:
    """Test Prometheus metrics endpoint is removed"""
    
    def test_metrics_endpoint_removed(self, client):
        """Test metrics endpoint returns 404"""
        response = client.get("/metrics")
        assert response.status_code == 404

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
