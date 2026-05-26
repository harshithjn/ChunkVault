# ChunkVault

**Production-Grade Distributed File Storage System** – A fault-tolerant, scalable, and highly available file storage solution built with Python, Flask, vanilla HTML/CSS/JS (served from Flask), PostgreSQL, Redis, and Celery.

## Core Features

- **User Authentication** – Secure JWT-based registration and login with local session caching.
- **File Slicing & Merging** – Large files are sliced into standard 4MB chunks for parallel storage and reconstructed dynamically on download.
- **Chunk Replication** – Synchronous replication factor of 3 across distinct distributed storage nodes (`node-1`, `node-2`, `node-3`) for quorum-based fault tolerance.
- **Expiring Shared Assets** – Temporary share tokens with a 24-hour automatic expiration, complete with a beautiful download lander.
- **Premium SPA Interface** – Modern glassmorphism dark-theme dashboard featuring real-time cluster health logs, stats gauges, category tracking progress rings, and interactive drag-and-drop uploads.
- **High-Performance Caching** – Redis integration to cache heavy file indexes, shared asset tokens, and binary chunk buffers to optimize high concurrency.
- **Observability** – Native Prometheus metrics collection for duration histograms, active socket tracking, and storage cluster pings.

## System Architecture

```
┌──────────────────────────────────────────────┐
│                  Client Browser              │
└──────────────────────┬───────────────────────┘
                       │ (HTTP/JSON on Port 8000)
                       ▼
┌──────────────────────────────────────────────┐
│           Flask Core API & Web UI            │
│             (Port 8000 / Single-Origin)      │
└──────────┬───────────┬───────────┬───────────┘
           │           │           │
           ▼           ▼           ▼
     ┌───────────┐┌─────────┐┌───────────┐
     │PostgreSQL ││  Redis  ││  Celery   │
     │(Metadata) ││ (Cache) ││ (Workers) │
     └───────────┘└────┬────┘└─────┬─────┘
                       │           │
                       ▼           ▼
┌──────────────────────────────────────────────┐
│               Storage Nodes                  │
│       Node-1      Node-2      Node-3         │
│     Port: 8001  Port: 8002  Port: 8003       │
└──────────────────────────────────────────────┘
```

## Running the Cluster Locally

Ensure you have [Docker](https://www.docker.com/) and Docker Compose installed.

### 1. Build and Run
Start the entire clustered system (PostgreSQL, Redis, Flask API, three storage nodes, Celery worker/beat scheduler, Prometheus, and Grafana) with a single command:
```bash
docker compose up --build
```

### 2. Access points
- **Web Dashboard & API**: [http://localhost:8000](http://localhost:8000)
  - Default Admin Account: `admin` / `admin123`
- **Prometheus Metrics**: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Grafana Panel**: [http://localhost:3000](http://localhost:3000) (Admin credentials: `admin` / `admin`)
- **Prometheus Dashboard**: [http://localhost:9090](http://localhost:9090)

## Running Unit Tests
To run the automated pytest suite locally:
```bash
PYTHONPATH=. pytest Scripts/test_chunkvault.py
```
