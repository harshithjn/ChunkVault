"""
ChunkVault Storage Node
Lightweight storage service for chunk storage and retrieval (Flask implementation)
"""
import os
import hashlib
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_file

# Configuration
NODE_ID = os.getenv("NODE_ID", "node-1")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))
STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "./storage"))
MAX_CHUNK_SIZE = 100 * 1024 * 1024  # 100MB

# Ensure storage directory exists
STORAGE_PATH.mkdir(parents=True, exist_ok=True)

# Flask application
app = Flask(__name__)

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

def get_storage_stats() -> dict:
    """Get storage statistics"""
    total_size = 0
    chunk_count = 0
    
    for root_dir, dirs, files in os.walk(STORAGE_PATH):
        for file in files:
            file_path = Path(root_dir) / file
            total_size += file_path.stat().st_size
            chunk_count += 1
            
    try:
        available_space = shutil.disk_usage(STORAGE_PATH).free
    except Exception:
        available_space = 1000 * 1024 * 1024  # 1GB fallback
        
    return {
        "total_size": total_size,
        "chunk_count": chunk_count,
        "available_space": available_space
    }

# CORS headers middleware
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response

@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "message": f"ChunkVault Storage Node {NODE_ID}",
        "version": "1.0.0",
        "node_id": NODE_ID
    }), 200

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        stats = get_storage_stats()
        return jsonify({
            "status": "healthy",
            "service": "storage_node",
            "node_id": NODE_ID,
            "storage_stats": stats
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

@app.route("/chunk/<chunk_id>", methods=["POST"])
def store_chunk(chunk_id):
    """Store a chunk"""
    try:
        # Supports raw octet-stream bytes or multipart form file upload
        if "file" in request.files:
            chunk_data = request.files["file"].read()
        else:
            chunk_data = request.data
            
        if not chunk_data:
            return jsonify({"detail": "Empty chunk data"}), 400
            
        # Validate size
        if len(chunk_data) > MAX_CHUNK_SIZE:
            return jsonify({"detail": f"Chunk size exceeds maximum allowed size of {MAX_CHUNK_SIZE} bytes"}), 413
            
        # Calculate checksum
        checksum = calculate_checksum(chunk_data)
        
        # Store chunk
        chunk_path = get_chunk_path(chunk_id)
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)
            
        return jsonify({
            "chunk_id": chunk_id,
            "checksum": checksum,
            "size": len(chunk_data),
            "status": "stored"
        }), 200
        
    except Exception as e:
        return jsonify({"detail": f"Error storing chunk: {str(e)}"}), 500

@app.route("/chunk/<chunk_id>", methods=["GET"])
def retrieve_chunk(chunk_id):
    """Retrieve a chunk"""
    try:
        chunk_path = get_chunk_path(chunk_id)
        
        if not chunk_path.exists():
            return jsonify({"detail": "Chunk not found"}), 404
            
        chunk_size = chunk_path.stat().st_size
        
        # Return chunk file stream
        response = send_file(
            chunk_path,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=chunk_id
        )
        response.headers["X-Chunk-ID"] = chunk_id
        response.headers["X-Chunk-Size"] = str(chunk_size)
        return response
        
    except Exception as e:
        return jsonify({"detail": f"Error retrieving chunk: {str(e)}"}), 500

@app.route("/chunk/<chunk_id>", methods=["DELETE"])
def delete_chunk(chunk_id):
    """Delete a chunk"""
    try:
        chunk_path = get_chunk_path(chunk_id)
        if chunk_path.exists():
            chunk_path.unlink()
        return jsonify({"chunk_id": chunk_id, "status": "deleted"}), 200
    except Exception as e:
        return jsonify({"detail": f"Error deleting chunk: {str(e)}"}), 500

@app.route("/chunk/<chunk_id>/info", methods=["GET"])
def get_chunk_info(chunk_id):
    """Get chunk information"""
    try:
        chunk_path = get_chunk_path(chunk_id)
        if not chunk_path.exists():
            return jsonify({"detail": "Chunk not found"}), 404
            
        chunk_size = chunk_path.stat().st_size
        return jsonify({
            "chunk_id": chunk_id,
            "size": chunk_size,
            "exists": True
        }), 200
    except Exception as e:
        return jsonify({"detail": f"Error getting chunk info: {str(e)}"}), 500

@app.route("/storage/stats", methods=["GET"])
def storage_stats():
    """Get storage node stats"""
    try:
        stats = get_storage_stats()
        return jsonify({
            "node_id": NODE_ID,
            "storage_stats": stats
        }), 200
    except Exception as e:
        return jsonify({"detail": f"Error getting storage stats: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
