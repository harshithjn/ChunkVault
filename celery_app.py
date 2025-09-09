"""
Celery configuration and task definitions for ChunkVault
"""
import os
from celery import Celery
from celery.schedules import crontab
import redis
import requests
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import Base, Chunk, ChunkReplica, File, FileShare

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery configuration
celery_app = Celery(
    "chunkvault",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["celery_app"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://chunkvault:chunkvault@localhost:5432/chunkvault")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Redis client for caching
redis_client = redis.from_url(REDIS_URL)

# Storage nodes configuration
STORAGE_NODES = [
    "http://localhost:8001",
    "http://localhost:8002", 
    "http://localhost:8003"
]

@celery_app.task(bind=True, name="chunkvault.replicate_chunk")
def replicate_chunk(self, chunk_id: str, chunk_data: bytes, storage_nodes: List[str], replication_factor: int = 3):
    """
    Replicate a chunk to multiple storage nodes
    """
    try:
        success_count = 0
        failed_nodes = []
        
        for node_url in storage_nodes:
            try:
                response = requests.post(
                    f"{node_url}/chunk/{chunk_id}",
                    data=chunk_data,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=30
                )
                if response.status_code == 200:
                    success_count += 1
                else:
                    failed_nodes.append(node_url)
            except Exception as e:
                failed_nodes.append(node_url)
                print(f"Failed to store chunk {chunk_id} to {node_url}: {e}")
        
        # Update chunk status in database
        db = SessionLocal()
        try:
            chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
            if chunk:
                if success_count >= (replication_factor // 2 + 1):  # Quorum
                    chunk.status = "stored"
                    # Create replica records for successful nodes
                    for node_url in storage_nodes:
                        if node_url not in failed_nodes:
                            replica = ChunkReplica(
                                id=f"{chunk_id}_{node_url}",
                                chunk_id=chunk_id,
                                storage_node_id=node_url
                            )
                            db.add(replica)
                else:
                    chunk.status = "failed"
                db.commit()
        finally:
            db.close()
        
        return {
            "chunk_id": chunk_id,
            "success_count": success_count,
            "failed_nodes": failed_nodes,
            "status": "stored" if success_count >= (replication_factor // 2 + 1) else "failed"
        }
        
    except Exception as e:
        self.retry(countdown=60, max_retries=3)
        raise e

@celery_app.task(name="chunkvault.verify_file_integrity")
def verify_file_integrity(file_id: str):
    """
    Verify file integrity by checking chunk checksums
    """
    try:
        db = SessionLocal()
        try:
            file_record = db.query(File).filter(File.id == file_id).first()
            if not file_record:
                return {"file_id": file_id, "status": "not_found"}
            
            chunks = db.query(Chunk).filter(Chunk.file_id == file_id).all()
            corrupted_chunks = []
            
            for chunk in chunks:
                # Get chunk data from storage nodes
                replicas = db.query(ChunkReplica).filter(ChunkReplica.chunk_id == chunk.id).all()
                storage_nodes = [replica.storage_node_id for replica in replicas]
                
                chunk_data = None
                for node_url in storage_nodes:
                    try:
                        response = requests.get(f"{node_url}/chunk/{chunk.id}", timeout=30)
                        if response.status_code == 200:
                            chunk_data = response.content
                            break
                    except:
                        continue
                
                if chunk_data:
                    # Verify checksum
                    calculated_checksum = hashlib.sha256(chunk_data).hexdigest()
                    if calculated_checksum != chunk.checksum:
                        corrupted_chunks.append({
                            "chunk_id": chunk.id,
                            "expected_checksum": chunk.checksum,
                            "calculated_checksum": calculated_checksum
                        })
                else:
                    corrupted_chunks.append({
                        "chunk_id": chunk.id,
                        "error": "chunk_not_found"
                    })
            
            # Update file status
            if corrupted_chunks:
                file_record.status = "corrupted"
            else:
                file_record.status = "verified"
            db.commit()
            
            return {
                "file_id": file_id,
                "status": "verified" if not corrupted_chunks else "corrupted",
                "corrupted_chunks": corrupted_chunks
            }
            
        finally:
            db.close()
            
    except Exception as e:
        return {"file_id": file_id, "status": "error", "error": str(e)}

@celery_app.task(name="chunkvault.cleanup_expired_shares")
def cleanup_expired_shares():
    """
    Clean up expired share links
    """
    try:
        db = SessionLocal()
        try:
            expired_shares = db.query(FileShare).filter(
                FileShare.expires_at < datetime.utcnow()
            ).all()
            
            count = len(expired_shares)
            for share in expired_shares:
                db.delete(share)
            
            db.commit()
            
            return {
                "status": "success",
                "expired_shares_removed": count
            }
            
        finally:
            db.close()
            
    except Exception as e:
        return {"status": "error", "error": str(e)}

@celery_app.task(name="chunkvault.health_check_storage_nodes")
def health_check_storage_nodes():
    """
    Check health of all storage nodes
    """
    try:
        node_status = {}
        
        for node_url in STORAGE_NODES:
            try:
                response = requests.get(f"{node_url}/health", timeout=10)
                if response.status_code == 200:
                    node_status[node_url] = {
                        "status": "healthy",
                        "response_time": response.elapsed.total_seconds()
                    }
                else:
                    node_status[node_url] = {
                        "status": "unhealthy",
                        "status_code": response.status_code
                    }
            except Exception as e:
                node_status[node_url] = {
                    "status": "offline",
                    "error": str(e)
                }
        
        # Cache the results in Redis
        redis_client.setex(
            "storage_nodes_health",
            300,  # 5 minutes
            str(node_status)
        )
        
        return {
            "status": "success",
            "node_status": node_status
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Periodic tasks
celery_app.conf.beat_schedule = {
    "cleanup-expired-shares": {
        "task": "chunkvault.cleanup_expired_shares",
        "schedule": crontab(minute=0, hour=2),  # Run daily at 2 AM
    },
    "health-check-storage-nodes": {
        "task": "chunkvault.health_check_storage_nodes",
        "schedule": 60.0,  # Run every minute
    },
    "verify-file-integrity": {
        "task": "chunkvault.verify_file_integrity",
        "schedule": crontab(minute=0, hour=3),  # Run daily at 3 AM
    },
}

if __name__ == "__main__":
    celery_app.start()
