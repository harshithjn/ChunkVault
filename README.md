# ChunkVault

**Production-Grade Distributed File Storage System** – A fault-tolerant, scalable file storage solution built with Python, FastAPI, Streamlit, PostgreSQL, Redis, Celery, and Kubernetes.

## Features

### Core Features

- User Authentication – Secure JWT-based login and registration
- File Management – Upload, download, and organize files using chunk-based storage
- File Sharing – Generate shareable links with expiration
- Chunk Replication – Files are split into chunks and replicated across storage nodes
- High Performance – Optimized for concurrent users with Redis caching
- Professional UI – Clean and modern Streamlit web interface

### Production Features

- PostgreSQL Database – Reliable metadata storage with migrations
- Redis Caching – Fast access to metadata and files
- Celery Workers – Asynchronous background processing
- Prometheus Metrics – System monitoring and observability
- Grafana Dashboards – Real-time analytics and monitoring
- Kubernetes Ready – Container orchestration with auto-scaling
- CI/CD Pipeline – Automated testing and deployment
- Docker Compose – Simple local development setup

## Architecture

### Production Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web UI        │    │   API Service   │    │  Storage Nodes  │
│  (Streamlit)    │◄──►│   (FastAPI)     │◄──►│   (FastAPI)     │
│   Port: 8501    │    │   Port: 8000    │    │ Ports: 8001-8003│
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PostgreSQL    │    │     Redis       │    │   Celery        │
│   (Metadata)    │◄──►│   (Cache/Queue) │◄──►│   (Workers)     │
│   Port: 5432    │    │   Port: 6379    │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Prometheus    │
                       │   + Grafana     │
                       │   (Monitoring)  │
                       └─────────────────┘
```
