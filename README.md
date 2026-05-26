# ChunkVault.
> **Clustered Object Storage System** – Cryptographic chunk partitioning, autonomous node replication, and multi-node quorum consensus. Resilient, minimal, and secure by design.

---

## Technical Features

* **Secure Authentication** – Cryptographically hashed registration and login console secured with JWT tokens and localized session cache.
* **Cryptographic Slicing** – Large assets are partitioned at the byte level into standardized 4MB segments with dynamic SHA-256 integrity hashing.
* **3x Quorum Replication** – Concurrent chunk distribution across distinct autonomous storage nodes (`node-1`, `node-2`, `node-3`) establishing solid fault-tolerant consensus.
* **Low-Latency Cache Locks** – Redis caching layers optimize indexed directory lookups, shared asset keys, and chunk routing paths.
* **Asynchronous Recovery Pipeline** – Decoupled Celery queue networks execute automated background audits to identify corrupted blocks and trigger self-healing routines.
* **Sleek Monochrome Interface** – High-contrast absolute black (`#000000`) and zinc (`#09090b`) single-page dashboard featuring razor-sharp wireframe grids and an interactive CSS cluster visualizer.
* **Secure Sharing Lander** – Unique shared download lander with expiring tokens (24-hour window) and instant file reassembly streaming.

---

## System Architecture

```text
       ┌────────────────────────────────────────────────────────┐
       │                     Client Browser                     │
       └───────────────────────────┬────────────────────────────┘
                                   │ (Port 8000: Unified SPA & API)
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │                 Flask Core API Server                  │
       └──────────────┬────────────┬────────────┬───────────────┘
                      │            │            │
                      ▼            ▼            ▼
               ┌──────────┐ ┌────────────┐ ┌──────────┐
               │PostgreSQL│ │Redis Cache │ │  Celery  │
               │(Metadata)│ │ & Broker   │ │ (Worker) │
               └──────────┘ └────────────┘ └────┬─────┘
                                                │ (Replication)
                                                ▼
       ┌────────────────────────────────────────────────────────┐
       │                 Autonomous Storage Nodes               │
       │     Node 1 (8001)     Node 2 (8002)     Node 3 (8003)  │
       └────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```text
├── app.py                     # Unified API and UI server (Flask)
├── Dockerfile                 # Multi-stage Docker container specification
├── docker-compose.yml         # 8-service distributed local orchestration stack
├── requirements.txt           # Lightened application dependencies
├── templates/
│   ├── index.html             # Corporate SaaS SPA Dashboard & Visualizer
│   └── share.html             # Secure shared asset download portal
├── Scripts/
│   ├── celery_app.py          # Asynchronous worker definition
│   ├── cache.py               # Low-latency Redis cache controller
│   ├── storage_node.py        # Lightweight Flask storage microservice
│   └── test_chunkvault.py     # Comprehensive 15-test pytest suite
└── storage/                   # Clustered storage directory mounts (Docker)
```

---

## Local Quick Start

### Prerequisites
Ensure you have [Docker Desktop](https://www.docker.com/) and Docker Compose installed.

### 1. Launch the Cluster
Boot the PostgreSQL database, Redis broker, main API container, 3 storage nodes, and Celery pipelines with one command:
```bash
docker compose up --build -d
```

### 2. Access Ports
- **Unified Dashboard Console**: [http://localhost:8000](http://localhost:8000)
- **Pre-configured Admin Access**:
  * **Username**: `admin`
  * **Password**: `admin123`

---

## Test Suite Execution

The automated verification suite tests authentication protocols, DB metadata creation, parallel chunk transfers, cache invalidations, and sharing tokens.

To run the test suite locally in your virtual environment:
```bash
DATABASE_URL=sqlite:///./test_chunkvault.db PYTHONPATH=. ./venv/bin/python -m pytest Scripts/test_chunkvault.py
```
*(Confirms **15 unit tests passed** successfully)*
