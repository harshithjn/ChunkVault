"""
ChunkVault - Distributed File Storage System
FastAPI application with integrated metadata service and storage management
"""
import os
import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import io
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
import uvicorn
import aiofiles
import requests
from concurrent.futures import ThreadPoolExecutor
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram, Gauge
import time

# Import our custom modules
from cache import cache_manager
from celery_app import replicate_chunk, verify_file_integrity

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "chunkvault-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
REPLICATION_FACTOR = 3
STORAGE_PATH = Path("./storage")
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

# Prometheus metrics
REQUEST_COUNT = Counter('chunkvault_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('chunkvault_request_duration_seconds', 'Request duration')
ACTIVE_CONNECTIONS = Gauge('chunkvault_active_connections', 'Active connections')
STORAGE_NODE_HEALTH = Gauge('chunkvault_storage_node_health', 'Storage node health', ['node_id'])
FILES_UPLOADED = Counter('chunkvault_files_uploaded_total', 'Total files uploaded')
FILES_DOWNLOADED = Counter('chunkvault_files_downloaded_total', 'Total files downloaded')
CHUNKS_STORED = Counter('chunkvault_chunks_stored_total', 'Total chunks stored')
CACHE_HITS = Counter('chunkvault_cache_hits_total', 'Cache hits', ['cache_type'])
CACHE_MISSES = Counter('chunkvault_cache_misses_total', 'Cache misses', ['cache_type'])

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Lifespan context manager
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and create default admin user"""
    Base.metadata.create_all(bind=engine)
    
    # Create default admin user
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                id="admin",
                username="admin",
                email="admin@chunkvault.com",
                password_hash=get_password_hash("admin123")
            )
            db.add(admin_user)
            db.commit()
            print("Created default admin user: admin/admin123")
    finally:
        db.close()
    
    yield
    
    # Cleanup code here if needed

# FastAPI app
app = FastAPI(
    title="ChunkVault",
    description="Distributed File Storage System",
    version="1.0.0",
    lifespan=lifespan
)

# Add Prometheus instrumentation
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add metrics middleware
@app.middleware("http")
async def metrics_middleware(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUEST_DURATION.observe(duration)
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    return response

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

# Pydantic Models
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class FileInfo(BaseModel):
    id: str
    filename: str
    size: int
    mime_type: str
    version: int
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ShareInfo(BaseModel):
    share_token: str
    share_url: str
    expires_at: Optional[datetime]
    
    class Config:
        from_attributes = True

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    return user

def calculate_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def assign_storage_nodes() -> List[str]:
    """Assign storage nodes for chunk replication"""
    import random
    return random.sample(STORAGE_NODES, min(REPLICATION_FACTOR, len(STORAGE_NODES)))

async def store_chunk_to_nodes(chunk_id: str, chunk_data: bytes, storage_nodes: List[str]) -> bool:
    """Store chunk to multiple storage nodes using Celery"""
    try:
        # Enqueue chunk replication task
        task = replicate_chunk.delay(chunk_id, chunk_data, storage_nodes, REPLICATION_FACTOR)
        
        # Wait for task completion with timeout
        result = task.get(timeout=60)
        
        if result and result.get("status") == "stored":
            CHUNKS_STORED.inc()
            return True
        else:
            return False
    except Exception as e:
        print(f"Failed to store chunk {chunk_id}: {e}")
        return False

async def retrieve_chunk_from_nodes(chunk_id: str, storage_nodes: List[str]) -> Optional[bytes]:
    """Retrieve chunk from storage nodes with caching"""
    # Check cache first
    cached_data = cache_manager.get_chunk_data(chunk_id)
    if cached_data:
        CACHE_HITS.labels(cache_type="chunk_data").inc()
        return cached_data
    
    CACHE_MISSES.labels(cache_type="chunk_data").inc()
    
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

# API Endpoints

@app.get("/")
async def root():
    return {"message": "ChunkVault API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint with storage node status"""
    # Get cached storage node health
    node_health = cache_manager.get_storage_node_health()
    if not node_health:
        # Fallback to direct check
        node_health = {}
        for node_url in STORAGE_NODES:
            try:
                response = requests.get(f"{node_url}/health", timeout=5)
                node_health[node_url] = "healthy" if response.status_code == 200 else "unhealthy"
            except:
                node_health[node_url] = "offline"
    
    return {
        "status": "healthy",
        "service": "chunkvault",
        "storage_nodes": node_health,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Authentication
@app.post("/auth/register")
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if user exists
    existing_user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create user
    user = User(
        id=str(uuid.uuid4()),
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {"message": "User created successfully", "user_id": user.id}

@app.post("/auth/login")
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login and get access token"""
    user = db.query(User).filter(User.username == user_data.username).first()
    
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id}

# File Management
@app.post("/files/upload")
async def upload_file(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a file"""
    try:
        # Read file data
        file_data = await file.read()
        file_size = len(file_data)
        file_checksum = calculate_checksum(file_data)
        
        # Create file record
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
        
        # Create chunks and store them
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
            
            # Assign storage nodes and store chunk
            storage_nodes = assign_storage_nodes()
            success = await store_chunk_to_nodes(chunk_id, chunk_data, storage_nodes)
            
            if success:
                chunk_record.status = "stored"
                # Create replica records
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
            # Enqueue file integrity verification
            verify_file_integrity.delay(file_id)
        
        db.commit()
        
        # Invalidate user files cache
        cache_manager.invalidate_user_files(current_user.id)
        
        # Update metrics
        FILES_UPLOADED.inc()
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "size": file_size,
            "chunk_count": chunk_count,
            "status": file_record.status
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/files")
async def list_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's files with caching"""
    # Check cache first
    cached_files = cache_manager.get_user_files(current_user.id)
    if cached_files:
        CACHE_HITS.labels(cache_type="user_files").inc()
        return cached_files
    
    CACHE_MISSES.labels(cache_type="user_files").inc()
    
    files = db.query(File).filter(File.owner_id == current_user.id).order_by(File.updated_at.desc()).all()
    file_list = [FileInfo.model_validate(file) for file in files]
    
    # Cache the results
    cache_manager.set_user_files(current_user.id, file_list)
    
    return file_list

@app.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download a file"""
    # Check cache for file metadata
    cached_metadata = cache_manager.get_file_metadata(file_id)
    if cached_metadata:
        CACHE_HITS.labels(cache_type="file_metadata").inc()
        file_record = File(**cached_metadata)
    else:
        CACHE_MISSES.labels(cache_type="file_metadata").inc()
        file_record = db.query(File).filter(
            File.id == file_id,
            File.owner_id == current_user.id
        ).first()
        
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Cache file metadata
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
    
    # Get chunks
    chunks = db.query(Chunk).filter(
        Chunk.file_id == file_id
    ).order_by(Chunk.chunk_index).all()
    
    # Retrieve chunk data
    chunk_data_list = []
    for chunk in chunks:
        replicas = db.query(ChunkReplica).filter(ChunkReplica.chunk_id == chunk.id).all()
        storage_nodes = [replica.storage_node_id for replica in replicas]
        
        chunk_data = await retrieve_chunk_from_nodes(chunk.id, storage_nodes)
        if chunk_data is None:
            raise HTTPException(status_code=500, detail=f"Failed to retrieve chunk {chunk.chunk_index}")
        
        chunk_data_list.append(chunk_data)
    
    # Combine chunks
    file_data = b''.join(chunk_data_list)
    
    # Update metrics
    FILES_DOWNLOADED.inc()
    
    return StreamingResponse(
        io.BytesIO(file_data),
        media_type=file_record.mime_type,
        headers={"Content-Disposition": f"attachment; filename={file_record.filename}"}
    )

@app.post("/files/{file_id}/share")
async def create_share(
    file_id: str,
    expires_in_hours: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a shareable link"""
    file_record = db.query(File).filter(
        File.id == file_id,
        File.owner_id == current_user.id
    ).first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Create share
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
    
    return ShareInfo(
        share_token=share_token,
        share_url=share_url,
        expires_at=expires_at
    )

@app.get("/share/{share_token}")
async def download_shared_file(share_token: str, db: Session = Depends(get_db)):
    """Download a shared file"""
    # Check cache for share info
    cached_share = cache_manager.get_share_info(share_token)
    if cached_share:
        CACHE_HITS.labels(cache_type="share_info").inc()
        share_record = FileShare(**cached_share)
    else:
        CACHE_MISSES.labels(cache_type="share_info").inc()
        share_record = db.query(FileShare).filter(FileShare.share_token == share_token).first()
        
        if not share_record:
            raise HTTPException(status_code=404, detail="Share not found")
        
        # Cache share info
        cache_manager.set_share_info(share_token, {
            "id": share_record.id,
            "file_id": share_record.file_id,
            "owner_id": share_record.owner_id,
            "share_token": share_record.share_token,
            "expires_at": share_record.expires_at,
            "created_at": share_record.created_at,
            "access_count": share_record.access_count
        })
    
    if share_record.expires_at and share_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Share has expired")
    
    # Increment access count
    share_record.access_count += 1
    db.commit()
    
    # Get file and download
    file_record = db.query(File).filter(File.id == share_record.file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get chunks and download (same logic as regular download)
    chunks = db.query(Chunk).filter(Chunk.file_id == file_record.id).order_by(Chunk.chunk_index).all()
    
    chunk_data_list = []
    for chunk in chunks:
        replicas = db.query(ChunkReplica).filter(ChunkReplica.chunk_id == chunk.id).all()
        storage_nodes = [replica.storage_node_id for replica in replicas]
        
        chunk_data = await retrieve_chunk_from_nodes(chunk.id, storage_nodes)
        if chunk_data is None:
            raise HTTPException(status_code=500, detail=f"Failed to retrieve chunk {chunk.chunk_index}")
        
        chunk_data_list.append(chunk_data)
    
    file_data = b''.join(chunk_data_list)
    
    # Update metrics
    FILES_DOWNLOADED.inc()
    
    return StreamingResponse(
        io.BytesIO(file_data),
        media_type=file_record.mime_type,
        headers={"Content-Disposition": f"attachment; filename={file_record.filename}"}
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
