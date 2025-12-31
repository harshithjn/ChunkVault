"""
Redis cache utilities for ChunkVault
"""
import json
import redis
import os
from typing import Any, Optional, Dict, List
from datetime import timedelta

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

class CacheManager:
    """Redis cache manager for ChunkVault"""
    
    def __init__(self):
        self.redis_client = redis_client
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            print(f"Cache get error for key {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in cache with optional expiration"""
        try:
            serialized_value = json.dumps(value, default=str)
            if expire:
                return self.redis_client.setex(key, expire, serialized_value)
            else:
                return self.redis_client.set(key, serialized_value)
        except Exception as e:
            print(f"Cache set error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            print(f"Cache delete error for key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            print(f"Cache exists error for key {key}: {e}")
            return False
    
    def get_user_files(self, user_id: str) -> Optional[List[Dict]]:
        """Get cached user files"""
        return self.get(f"user_files:{user_id}")
    
    def set_user_files(self, user_id: str, files: List[Dict], expire: int = 300) -> bool:
        """Cache user files for 5 minutes"""
        return self.set(f"user_files:{user_id}", files, expire)
    
    def invalidate_user_files(self, user_id: str) -> bool:
        """Invalidate user files cache"""
        return self.delete(f"user_files:{user_id}")
    
    def get_file_metadata(self, file_id: str) -> Optional[Dict]:
        """Get cached file metadata"""
        return self.get(f"file_metadata:{file_id}")
    
    def set_file_metadata(self, file_id: str, metadata: Dict, expire: int = 600) -> bool:
        """Cache file metadata for 10 minutes"""
        return self.set(f"file_metadata:{file_id}", metadata, expire)
    
    def invalidate_file_metadata(self, file_id: str) -> bool:
        """Invalidate file metadata cache"""
        return self.delete(f"file_metadata:{file_id}")
    
    def get_storage_stats(self) -> Optional[Dict]:
        """Get cached storage statistics"""
        return self.get("storage_stats")
    
    def set_storage_stats(self, stats: Dict, expire: int = 60) -> bool:
        """Cache storage statistics for 1 minute"""
        return self.set("storage_stats", stats, expire)
    
    def get_storage_node_health(self) -> Optional[Dict]:
        """Get cached storage node health"""
        return self.get("storage_nodes_health")
    
    def set_storage_node_health(self, health: Dict, expire: int = 300) -> bool:
        """Cache storage node health for 5 minutes"""
        return self.set("storage_nodes_health", health, expire)
    
    def get_chunk_data(self, chunk_id: str) -> Optional[bytes]:
        """Get cached chunk data"""
        try:
            return self.redis_client.get(f"chunk_data:{chunk_id}")
        except Exception as e:
            print(f"Cache get chunk data error for {chunk_id}: {e}")
            return None
    
    def set_chunk_data(self, chunk_id: str, data: bytes, expire: int = 3600) -> bool:
        """Cache chunk data for 1 hour"""
        try:
            return self.redis_client.setex(f"chunk_data:{chunk_id}", expire, data)
        except Exception as e:
            print(f"Cache set chunk data error for {chunk_id}: {e}")
            return False
    
    def invalidate_chunk_data(self, chunk_id: str) -> bool:
        """Invalidate chunk data cache"""
        return self.delete(f"chunk_data:{chunk_id}")
    
    def get_share_info(self, share_token: str) -> Optional[Dict]:
        """Get cached share information"""
        return self.get(f"share_info:{share_token}")
    
    def set_share_info(self, share_token: str, share_info: Dict, expire: int = 1800) -> bool:
        """Cache share information for 30 minutes"""
        return self.set(f"share_info:{share_token}", share_info, expire)
    
    def invalidate_share_info(self, share_token: str) -> bool:
        """Invalidate share information cache"""
        return self.delete(f"share_info:{share_token}")

# Global cache manager instance
cache_manager = CacheManager()
