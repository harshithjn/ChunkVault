"""
ChunkVault Storage Node
Lightweight storage service for chunk storage and retrieval
"""
import os
import asyncio
import aiofiles
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
import io
import hashlib
import shutil

# Configuration
NODE_ID = os.getenv("NODE_ID", "node-1")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))
STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "./storage"))
MAX_CHUNK_SIZE = 100 * 1024 * 1024  # 100MB

# Ensure storage directory exists
STORAGE_PATH.mkdir(parents=True, exist_ok=True)

def get_chunk_path(chunk_id: str) -> Path:
    """Get the file path for a chunk"""
    # Use first 2 characters as subdirectory for organization
    subdir = chunk_id[:2]
    chunk_dir = STORAGE_PATH / subdir
    chunk_dir.mkdir(exist_ok=True)
    return chunk_dir / chunk_id

def calculate_checksum(data: bytes) -> str:
    """Calculate SHA-256 checksum"""
    return hashlib.sha256(data).hexdigest()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize storage node"""
    print(f"Storage node {NODE_ID} started on {HOST}:{PORT}")
    print(f"Storage path: {STORAGE_PATH.absolute()}")
    yield

# FastAPI app
app = FastAPI(
    title=f"ChunkVault Storage Node {NODE_ID}",
    description="Storage node service for distributed file storage",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": f"ChunkVault Storage Node {NODE_ID}",
        "version": "1.0.0",
        "node_id": NODE_ID
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        stats = get_storage_stats()
        return {
            "status": "healthy",
            "service": "storage_node",
            "node_id": NODE_ID,
            "storage_stats": stats
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.post("/chunk/{chunk_id}")
async def store_chunk(chunk_id: str, file: UploadFile = File(...)):
    """Store a chunk"""
    try:
        # Read chunk data
        chunk_data = await file.read()
        
        # Validate chunk size
        if len(chunk_data) > MAX_CHUNK_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Chunk size exceeds maximum allowed size of {MAX_CHUNK_SIZE} bytes"
            )
        
        # Calculate checksum
        checksum = calculate_checksum(chunk_data)
        
        # Store chunk
        chunk_path = get_chunk_path(chunk_id)
        async with aiofiles.open(chunk_path, "wb") as f:
            await f.write(chunk_data)
        
        return {
            "chunk_id": chunk_id,
            "checksum": checksum,
            "size": len(chunk_data),
            "status": "stored"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error storing chunk: {str(e)}"
        )

@app.get("/chunk/{chunk_id}")
async def retrieve_chunk(chunk_id: str):
    """Retrieve a chunk"""
    try:
        chunk_path = get_chunk_path(chunk_id)
        
        if not chunk_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chunk not found"
            )
        
        # Read chunk data
        async with aiofiles.open(chunk_path, "rb") as f:
            chunk_data = await f.read()
        
        # Return chunk as streaming response
        return StreamingResponse(
            io.BytesIO(chunk_data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={chunk_id}",
                "X-Chunk-ID": chunk_id,
                "X-Chunk-Size": str(len(chunk_data))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving chunk: {str(e)}"
        )

@app.delete("/chunk/{chunk_id}")
async def delete_chunk(chunk_id: str):
    """Delete a chunk"""
    try:
        chunk_path = get_chunk_path(chunk_id)
        
        if chunk_path.exists():
            chunk_path.unlink()
        
        return {"chunk_id": chunk_id, "status": "deleted"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting chunk: {str(e)}"
        )

@app.get("/chunk/{chunk_id}/info")
async def get_chunk_info(chunk_id: str):
    """Get chunk information"""
    try:
        chunk_path = get_chunk_path(chunk_id)
        
        if not chunk_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chunk not found"
            )
        
        chunk_size = chunk_path.stat().st_size
        
        return {
            "chunk_id": chunk_id,
            "size": chunk_size,
            "exists": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting chunk info: {str(e)}"
        )

def get_storage_stats() -> dict:
    """Get storage statistics"""
    total_size = 0
    chunk_count = 0
    
    for root, dirs, files in os.walk(STORAGE_PATH):
        for file in files:
            file_path = Path(root) / file
            total_size += file_path.stat().st_size
            chunk_count += 1
    
    return {
        "total_size": total_size,
        "chunk_count": chunk_count,
        "available_space": shutil.disk_usage(STORAGE_PATH).free
    }

@app.get("/storage/stats")
async def storage_stats():
    """Get storage statistics"""
    try:
        stats = get_storage_stats()
        return {
            "node_id": NODE_ID,
            "storage_stats": stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting storage stats: {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
