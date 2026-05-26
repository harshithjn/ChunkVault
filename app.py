"""
ChunkVault - Distributed File Storage System
Flask application with integrated metadata service and storage management
"""
import os
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path
from functools import wraps

from flask import Flask, request, jsonify, render_template, Response
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import io
from passlib.context import CryptContext
from jose import JWTError, jwt
import requests
from celery import Celery
import time

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "chunkvault-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
REPLICATION_FACTOR = 3
STORAGE_PATH = Path("./storage")
STORAGE_NODES_ENV = os.getenv("STORAGE_NODES")
if STORAGE_NODES_ENV:
    STORAGE_NODES = STORAGE_NODES_ENV.split(",")
else:
    STORAGE_NODES = [
        "http://localhost:8001",
        "http://localhost:8002", 
        "http://localhost:8003"
    ]

# Database setup - PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://chunkvault:chunkvault@localhost:5432/chunkvault")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Security
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Flask app configuration
app = Flask(__name__, template_folder="templates")

# Import custom cache manager
from Scripts.cache import cache_manager

# Database Models
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    files = relationship("File", back_populates="owner")

class File(Base):
    __tablename__ = "files"
    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    size = Column(Integer, nullable=False)
    mime_type = Column(String, nullable=False)
    version = Column(Integer, default=1)
    status = Column(String, default="uploading")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    checksum = Column(String, nullable=False)
    chunk_count = Column(Integer, nullable=False)
    owner = relationship("User", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")

class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(String, primary_key=True)
    file_id = Column(String, ForeignKey("files.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    size = Column(Integer, nullable=False)
    checksum = Column(String, nullable=False)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    file = relationship("File", back_populates="chunks")
    replicas = relationship("ChunkReplica", back_populates="chunk", cascade="all, delete-orphan")

class ChunkReplica(Base):
    __tablename__ = "chunk_replicas"
    id = Column(String, primary_key=True)
    chunk_id = Column(String, ForeignKey("chunks.id"), nullable=False)
    storage_node_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    chunk = relationship("Chunk", back_populates="replicas")

class FileShare(Base):
    __tablename__ = "file_shares"
    id = Column(String, primary_key=True)
    file_id = Column(String, ForeignKey("files.id"), nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    share_token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    access_count = Column(Integer, default=0)

# Create Celery client to dispatch tasks by name (decouples circular imports)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_client = Celery("chunkvault", broker=REDIS_URL, backend=REDIS_URL)

# Initialize database schemas and default admin user inside app context
with app.app_context():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                id="admin",
                username="admin",
                email="admin@chunkvault.com",
                password_hash=pwd_context.hash("admin123")
            )
            db.add(admin_user)
            db.commit()
            print("Created default admin user: admin/admin123")
    finally:
        db.close()

# Utility Functions
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def calculate_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def assign_storage_nodes() -> List[str]:
    """Assign storage nodes for chunk replication"""
    import random
    return random.sample(STORAGE_NODES, min(REPLICATION_FACTOR, len(STORAGE_NODES)))

def store_chunk_to_nodes_sync(chunk_id: str, chunk_data: bytes, storage_nodes: List[str]) -> bool:
    """Store chunk to multiple storage nodes using Celery (synchronous)"""
    try:
        # Enqueue chunk replication task by name
        task = celery_client.send_task("chunkvault.replicate_chunk", args=[chunk_id, chunk_data, storage_nodes, REPLICATION_FACTOR])
        # Wait for task completion with timeout
        result = task.get(timeout=60)
        
        if result and result.get("status") == "stored":
            return True
        else:
            return False
    except Exception as e:
        print(f"Failed to store chunk {chunk_id}: {e}")
        return False

def retrieve_chunk_from_nodes_sync(chunk_id: str, storage_nodes: List[str]) -> Optional[bytes]:
    """Retrieve chunk from storage nodes with caching (synchronous)"""
    # Check cache first
    cached_data = cache_manager.get_chunk_data(chunk_id)
    if cached_data:
        if isinstance(cached_data, str):
            return cached_data.encode('utf-8')
        return cached_data
    
    for node_url in storage_nodes:
        try:
            response = requests.get(f"{node_url}/chunk/{chunk_id}", timeout=30)
            if response.status_code == 200:
                chunk_data = response.content
                # Cache the chunk data
                cache_manager.set_chunk_data(chunk_id, chunk_data)
                return chunk_data
        except Exception as e:
            print(f"Failed to retrieve chunk {chunk_id} from {node_url}: {e}")
    
    return None

def format_file_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"

# Custom Token Security Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({"detail": "Token formatting error"}), 401
        
        if not token:
            return jsonify({"detail": "Authorization token is missing"}), 401
        
        payload = verify_token(token)
        if not payload:
            return jsonify({"detail": "Could not validate credentials"}), 401
        
        user_id = payload.get("sub")
        db = SessionLocal()
        try:
            current_user = db.query(User).filter(User.id == user_id).first()
            if not current_user:
                return jsonify({"detail": "User not found"}), 401
            
            return f(current_user, db, *args, **kwargs)
        finally:
            db.close()
    return decorated

# CORS middleware equivalent
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response

# Page Servings
@app.route("/")
def index():
    """Serves the premium single-page dashboard"""
    return render_template("index.html")

@app.route("/share/<share_token>")
def share_landing(share_token):
    """Serves a gorgeous landing lander for file sharing links"""
    db = SessionLocal()
    try:
        share_record = db.query(FileShare).filter(FileShare.share_token == share_token).first()
        if not share_record:
            return render_template("share.html", error=True)
        
        if share_record.expires_at and share_record.expires_at < datetime.utcnow():
            return render_template("share.html", error=True)
        
        file_record = db.query(File).filter(File.id == share_record.file_id).first()
        if not file_record:
            return render_template("share.html", error=True)
        
        return render_template(
            "share.html",
            error=False,
            filename=file_record.filename,
            size_formatted=format_file_size(file_record.size),
            share_token=share_token
        )
    finally:
        db.close()

# REST Authentication endpoints
@app.route("/api/auth/register", methods=["POST"])
def register():
    """Register a new user"""
    data = request.get_json()
    if not data or not data.get("username") or not data.get("email") or not data.get("password"):
        return jsonify({"detail": "Missing username, email or password"}), 400
    
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(
            (User.username == data["username"]) | (User.email == data["email"])
        ).first()
        if existing_user:
            return jsonify({"detail": "Username or email already registered"}), 400
        
        user = User(
            id=str(uuid.uuid4()),
            username=data["username"],
            email=data["email"],
            password_hash=get_password_hash(data["password"])
        )
        db.add(user)
        db.commit()
        return jsonify({"message": "User created successfully", "user_id": user.id}), 200
    except Exception as e:
        db.rollback()
        return jsonify({"detail": f"Registration failed: {str(e)}"}), 500
    finally:
        db.close()

@app.route("/api/auth/login", methods=["POST"])
def login():
    """Login and acquire secure JWT bearer token"""
    data = request.get_json()
    if not data or not data.get("username") or not data.get("password"):
        return jsonify({"detail": "Missing username or password"}), 400
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == data["username"]).first()
        if not user or not verify_password(data["password"], user.password_hash):
            return jsonify({"detail": "Incorrect username or password"}), 401
        
        access_token = create_access_token(data={"sub": user.id})
        return jsonify({"access_token": access_token, "token_type": "bearer", "user_id": user.id}), 200
    finally:
        db.close()

# File management endpoints
@app.route("/api/files/upload", methods=["POST"])
@token_required
def upload_file(current_user, db):
    """Upload and slice a file, then replicate blocks across nodes"""
    if "file" not in request.files:
        return jsonify({"detail": "No file parameter in request"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"detail": "No selected file"}), 400
    
    try:
        # Read file data
        file_data = file.read()
        file_size = len(file_data)
        file_checksum = calculate_checksum(file_data)
        
        file_id = str(uuid.uuid4())
        chunk_count = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        file_record = File(
            id=file_id,
            filename=file.filename,
            owner_id=current_user.id,
            size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            checksum=file_checksum,
            chunk_count=chunk_count,
            status="uploading"
        )
        db.add(file_record)
        
        # Slicing file and replicates to cluster nodes
        chunks = []
        for i in range(chunk_count):
            start = i * CHUNK_SIZE
            end = min(start + CHUNK_SIZE, file_size)
            chunk_data = file_data[start:end]
            chunk_checksum = calculate_checksum(chunk_data)
            
            chunk_id = str(uuid.uuid4())
            chunk_record = Chunk(
                id=chunk_id,
                file_id=file_id,
                chunk_index=i,
                size=len(chunk_data),
                checksum=chunk_checksum,
                status="pending"
            )
            db.add(chunk_record)
            
            storage_nodes = assign_storage_nodes()
            success = store_chunk_to_nodes_sync(chunk_id, chunk_data, storage_nodes)
            
            if success:
                chunk_record.status = "stored"
                for node_url in storage_nodes:
                    replica = ChunkReplica(
                        id=f"{chunk_id}_{node_url}",
                        chunk_id=chunk_id,
                        storage_node_id=node_url
                    )
                    db.add(replica)
            else:
                chunk_record.status = "failed"
                file_record.status = "failed"
                break
            
            chunks.append(chunk_record)
        
        if file_record.status != "failed":
            file_record.status = "completed"
            # Background Celery task triggers file integrity validation
            celery_client.send_task("chunkvault.verify_file_integrity", args=[file_id])
        
        db.commit()
        
        # Invalidate cache
        cache_manager.invalidate_user_files(current_user.id)
        
        return jsonify({
            "file_id": file_id,
            "filename": file.filename,
            "size": file_size,
            "chunk_count": chunk_count,
            "status": file_record.status
        }), 200
        
    except Exception as e:
        db.rollback()
        return jsonify({"detail": f"Upload failed: {str(e)}"}), 500

@app.route("/api/files", methods=["GET"])
@token_required
def list_files(current_user, db):
    """Lists metadata records of user's files with Redis caching"""
    cached_files = cache_manager.get_user_files(current_user.id)
    if cached_files:
        return jsonify(cached_files), 200
    
    files = db.query(File).filter(File.owner_id == current_user.id).order_by(File.updated_at.desc()).all()
    file_list = []
    for file in files:
        file_list.append({
            "id": file.id,
            "filename": file.filename,
            "size": file.size,
            "mime_type": file.mime_type,
            "version": file.version,
            "status": file.status,
            "created_at": file.created_at.isoformat() + "Z",
            "updated_at": file.updated_at.isoformat() + "Z"
        })
    
    cache_manager.set_user_files(current_user.id, file_list)
    return jsonify(file_list), 200

@app.route("/api/files/<file_id>/download", methods=["GET"])
@token_required
def download_file(current_user, db, file_id):
    """Retrieve chunk replicas from storage clusters, merge blocks, and stream download"""
    cached_metadata = cache_manager.get_file_metadata(file_id)
    if cached_metadata:
        filename = cached_metadata["filename"]
        mime_type = cached_metadata["mime_type"]
    else:
        file_record = db.query(File).filter(
            File.id == file_id,
            File.owner_id == current_user.id
        ).first()
        
        if not file_record:
            return jsonify({"detail": "File not found"}), 404
        
        filename = file_record.filename
        mime_type = file_record.mime_type
        
        cache_manager.set_file_metadata(file_id, {
            "id": file_record.id,
            "filename": file_record.filename,
            "owner_id": file_record.owner_id,
            "size": file_record.size,
            "mime_type": file_record.mime_type,
            "version": file_record.version,
            "status": file_record.status,
            "created_at": file_record.created_at,
            "updated_at": file_record.updated_at,
            "checksum": file_record.checksum,
            "chunk_count": file_record.chunk_count
        })
    
    chunks = db.query(Chunk).filter(Chunk.file_id == file_id).order_by(Chunk.chunk_index).all()
    chunk_data_list = []
    for chunk in chunks:
        replicas = db.query(ChunkReplica).filter(ChunkReplica.chunk_id == chunk.id).all()
        storage_nodes = [replica.storage_node_id for replica in replicas]
        
        chunk_data = retrieve_chunk_from_nodes_sync(chunk.id, storage_nodes)
        if chunk_data is None:
            return jsonify({"detail": f"Failed to retrieve chunk {chunk.chunk_index}"}), 500
        
        chunk_data_list.append(chunk_data)
    
    file_data = b''.join(chunk_data_list)
    
    return Response(
        file_data,
        mimetype=mime_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/api/files/<file_id>/share", methods=["POST"])
@token_required
def create_share(current_user, db, file_id):
    """Generate unique, expiring (24h) sharing token for vault files"""
    file_record = db.query(File).filter(
        File.id == file_id,
        File.owner_id == current_user.id
    ).first()
    
    if not file_record:
        return jsonify({"detail": "File not found"}), 404
    
    expires_in_hours = request.args.get("expires_in_hours", type=int)
    if not expires_in_hours:
        try:
            data = request.get_json(silent=True)
            if data:
                expires_in_hours = data.get("expires_in_hours")
        except:
            pass
            
    share_token = str(uuid.uuid4())
    expires_at = None
    if expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
    
    share_record = FileShare(
        id=str(uuid.uuid4()),
        file_id=file_id,
        owner_id=current_user.id,
        share_token=share_token,
        expires_at=expires_at
    )
    db.add(share_record)
    db.commit()
    
    share_url = f"/share/{share_token}"
    return jsonify({
        "share_token": share_token,
        "share_url": share_url,
        "expires_at": expires_at.isoformat() + "Z" if expires_at else None
    }), 200

@app.route("/api/share/<share_token>/download", methods=["GET"])
def download_shared_file_api(share_token):
    """Triggers file streaming download via public share link"""
    db = SessionLocal()
    try:
        share_record = db.query(FileShare).filter(FileShare.share_token == share_token).first()
        if not share_record:
            return jsonify({"detail": "Share not found"}), 404
        
        if share_record.expires_at and share_record.expires_at < datetime.utcnow():
            return jsonify({"detail": "Share has expired"}), 410
        
        # Increment access count
        share_record.access_count += 1
        db.commit()
        
        file_record = db.query(File).filter(File.id == share_record.file_id).first()
        if not file_record:
            return jsonify({"detail": "File not found"}), 404
        
        chunks = db.query(Chunk).filter(Chunk.file_id == file_record.id).order_by(Chunk.chunk_index).all()
        chunk_data_list = []
        for chunk in chunks:
            replicas = db.query(ChunkReplica).filter(ChunkReplica.chunk_id == chunk.id).all()
            storage_nodes = [replica.storage_node_id for replica in replicas]
            
            chunk_data = retrieve_chunk_from_nodes_sync(chunk.id, storage_nodes)
            if chunk_data is None:
                return jsonify({"detail": f"Failed to retrieve chunk {chunk.chunk_index}"}), 500
            
            chunk_data_list.append(chunk_data)
        
        file_data = b''.join(chunk_data_list)
        
        return Response(
            file_data,
            mimetype=file_record.mime_type,
            headers={"Content-Disposition": f"attachment; filename={file_record.filename}"}
        )
    finally:
        db.close()

# Monitoring/Health APIs
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint mapping registered storage nodes statuses"""
    node_health = cache_manager.get_storage_node_health()
    if not node_health:
        node_health = {}
        for node_url in STORAGE_NODES:
            try:
                response = requests.get(f"{node_url}/health", timeout=5)
                node_health[node_url] = "healthy" if response.status_code == 200 else "unhealthy"
            except:
                node_health[node_url] = "offline"
    
    return jsonify({
        "status": "healthy",
        "service": "chunkvault",
        "storage_nodes": node_health,
        "timestamp": datetime.utcnow().isoformat()
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
