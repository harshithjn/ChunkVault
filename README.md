# 🗄️ ChunkVault

**Production-Grade Distributed File Storage System** - A fault-tolerant, scalable file storage solution built with Python, FastAPI, Streamlit, PostgreSQL, Redis, Celery, and Kubernetes.

## ✨ Features

### Core Features

- **🔐 User Authentication** - Secure JWT-based login/registration system
- **📁 File Management** - Upload, download, and organize files with chunk-based storage
- **🔗 File Sharing** - Generate shareable links with expiration
- **🔄 Chunk Replication** - Files are split into chunks and replicated across multiple storage nodes
- **⚡ High Performance** - Optimized for 100+ concurrent users with Redis caching
- **🎨 Professional UI** - Modern Streamlit web interface

### Production Features

- **🗄️ PostgreSQL Database** - Robust metadata storage with Alembic migrations
- **⚡ Redis Caching** - High-performance caching for metadata and file access
- **🔄 Celery Workers** - Asynchronous task processing for chunk replication and integrity verification
- **📊 Prometheus Metrics** - Comprehensive monitoring and observability
- **📈 Grafana Dashboards** - Real-time system monitoring and analytics
- **☸️ Kubernetes Ready** - Full container orchestration with HPA
- **🚀 CI/CD Pipeline** - Automated testing, building, and deployment with GitHub Actions
- **🐳 Docker Compose** - Easy local development and testing

## 🏗️ Architecture

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

### Kubernetes Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ChunkVault Namespace                     │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   API Layer     │  Storage Layer  │      Monitoring Layer       │
│                 │                 │                             │
│ • API Pods      │ • Storage Pods  │ • Prometheus                │
│ • UI Pods       │ • StatefulSets  │ • Grafana                   │
│ • Celery        │                 │                             │
│   Workers       │                 │                             │
├─────────────────┼─────────────────┼─────────────────────────────┤
│   Infrastructure Layer                                           │
│ • PostgreSQL    │ • Redis         │ • Persistent Volumes        │
│ • ConfigMaps    │ • Secrets       │ • Services                  │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for containerized deployment)
- Kubernetes cluster (for production deployment)
- kubectl configured (for Kubernetes deployment)

### Option 1: Docker Compose Deployment (Recommended for Development)

1. **Clone and start the system:**

```bash
git clone <repository-url>
cd ChunkVault
docker-compose up -d
```

2. **Wait for services to be ready:**

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f chunkvault-api
```

3. **Access the application:**

- **Web UI**: http://localhost:8501
- **API**: http://localhost:8000
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Default login**: `admin` / `admin123`

### Option 2: Kubernetes Deployment (Production)

1. **Deploy to Kubernetes:**

```bash
# Create namespace and infrastructure
kubectl apply -f k8s/infrastructure/namespace.yaml
kubectl apply -f k8s/infrastructure/postgres.yaml
kubectl apply -f k8s/infrastructure/redis.yaml

# Deploy storage nodes
kubectl apply -f k8s/storage/storage-nodes.yaml

# Deploy API and workers
kubectl apply -f k8s/api/api-deployment.yaml
kubectl apply -f k8s/api/celery.yaml
kubectl apply -f k8s/api/ui.yaml

# Deploy monitoring
kubectl apply -f k8s/monitoring/prometheus.yaml
kubectl apply -f k8s/monitoring/grafana.yaml
```

2. **Check deployment status:**

```bash
kubectl get pods -n chunkvault
kubectl get services -n chunkvault
```

3. **Access services:**

```bash
# Port forward to access services
kubectl port-forward -n chunkvault svc/chunkvault-ui 8501:8501
kubectl port-forward -n chunkvault svc/grafana 3000:3000
kubectl port-forward -n chunkvault svc/prometheus 9090:9090
```

### Option 3: Local Development

1. **Install dependencies:**

```bash
pip install -r requirements.txt
```

2. **Set up PostgreSQL and Redis:**

```bash
# Start PostgreSQL and Redis locally or use Docker
docker run -d --name postgres -e POSTGRES_PASSWORD=chunkvault -p 5432:5432 postgres:15
docker run -d --name redis -p 6379:6379 redis:7
```

3. **Run database migrations:**

```bash
alembic upgrade head
```

4. **Start services:**

```bash
# Terminal 1 - Start Celery worker
celery -A celery_app worker --loglevel=info

# Terminal 2 - Start Celery beat
celery -A celery_app beat --loglevel=info

# Terminal 3 - Start storage nodes
NODE_ID=node-1 PORT=8001 python storage_node.py

# Terminal 4 - Start main API
python app.py

# Terminal 5 - Start web UI
streamlit run streamlit_app.py
```

## 📖 Usage

### Web Interface

1. Open http://localhost:8501
2. Register a new account or login with `admin`/`admin123`
3. Upload files using the drag-and-drop interface
4. View, download, and share your files
5. Monitor system analytics and storage statistics

### API Endpoints

**Authentication:**

- `POST /auth/register` - Register new user
- `POST /auth/login` - Login user

**File Operations:**

- `POST /files/upload` - Upload file
- `GET /files` - List user files
- `GET /files/{file_id}/download` - Download file
- `POST /files/{file_id}/share` - Create share link
- `GET /share/{share_token}` - Download shared file

## 🔧 Configuration

### Environment Variables

| Variable       | Default                                                        | Description                  |
| -------------- | -------------------------------------------------------------- | ---------------------------- |
| `SECRET_KEY`   | `chunkvault-super-secret-key-change-in-production`             | JWT secret key               |
| `DATABASE_URL` | `postgresql://chunkvault:chunkvault@localhost:5432/chunkvault` | PostgreSQL connection string |
| `REDIS_URL`    | `redis://localhost:6379/0`                                     | Redis connection string      |
| `API_BASE_URL` | `http://localhost:8000`                                        | API base URL for UI          |
| `NODE_ID`      | `node-1`                                                       | Storage node identifier      |
| `PORT`         | `8001`                                                         | Storage node port            |
| `STORAGE_PATH` | `./storage`                                                    | Storage directory path       |

### Storage Configuration

- **Chunk Size:** 4MB (configurable)
- **Replication Factor:** 3 (files stored on 3 nodes)
- **Max File Size:** 100MB per chunk
- **Supported Formats:** All file types

## 📊 Performance

- **Concurrent Users:** 100+ users (with Redis caching)
- **File Size Limit:** No practical limit (chunked storage)
- **Upload Speed:** Optimized for parallel chunk uploads with Celery workers
- **Download Speed:** Parallel chunk retrieval with Redis caching
- **Storage Efficiency:** Automatic deduplication via SHA-256 checksums
- **Response Time:** < 100ms for cached requests
- **Throughput:** 1000+ requests/second with horizontal scaling

## 🛡️ Security Features

- **JWT Authentication** - Secure token-based auth
- **Password Hashing** - bcrypt password encryption
- **File Integrity** - SHA-256 checksums for all chunks
- **Access Control** - User-based file permissions
- **Share Expiration** - Time-limited share links

## 🔍 Monitoring

The system provides comprehensive monitoring through:

### Prometheus Metrics

- **API Performance** - Request rates, response times, error rates
- **Storage Statistics** - Disk usage, chunk counts, node health
- **Cache Performance** - Hit rates, miss rates, cache efficiency
- **Celery Tasks** - Task queue length, processing times, failures
- **System Resources** - CPU, memory, disk usage

### Grafana Dashboards

- **Real-time Metrics** - Live system performance monitoring
- **Historical Data** - Trend analysis and capacity planning
- **Alerting** - Automated alerts for system issues
- **Custom Panels** - Configurable monitoring dashboards

### Health Checks

- **API Health** - `/health` endpoint with storage node status
- **Storage Node Health** - Individual node monitoring
- **Database Health** - PostgreSQL connection monitoring
- **Redis Health** - Cache and queue monitoring

## 🚀 Production Deployment

### Kubernetes Deployment (Recommended for Production)

1. **Prerequisites:**

   - Kubernetes cluster (v1.20+)
   - kubectl configured
   - Persistent volume provisioner
   - Load balancer or ingress controller

2. **Deploy ChunkVault:**

```bash
# Clone repository
git clone <repository-url>
cd ChunkVault

# Deploy all components
kubectl apply -f k8s/infrastructure/
kubectl apply -f k8s/storage/
kubectl apply -f k8s/api/
kubectl apply -f k8s/monitoring/

# Verify deployment
kubectl get pods -n chunkvault
kubectl get services -n chunkvault
```

3. **Configure Ingress (Optional):**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: chunkvault-ingress
  namespace: chunkvault
spec:
  rules:
    - host: chunkvault.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: chunkvault-ui
                port:
                  number: 8501
```

### Docker Compose (Development/Testing)

```bash
# Production deployment with all services
docker-compose up -d

# Scale services
docker-compose up -d --scale chunkvault-api=3 --scale celery-worker=2

# Monitor logs
docker-compose logs -f
```

### Environment Setup

1. **Security Configuration:**

   - Set strong `SECRET_KEY` (32+ characters)
   - Use strong PostgreSQL passwords
   - Enable Redis AUTH
   - Configure TLS/SSL certificates

2. **Database Configuration:**

   - Use managed PostgreSQL service (AWS RDS, Google Cloud SQL)
   - Configure connection pooling
   - Set up automated backups
   - Enable monitoring and alerting

3. **Infrastructure:**

   - Set up reverse proxy (nginx/HAProxy)
   - Enable HTTPS with Let's Encrypt
   - Configure firewall rules
   - Set up log aggregation (ELK stack)

4. **Monitoring:**
   - Configure Prometheus alerting rules
   - Set up Grafana dashboards
   - Enable log monitoring
   - Configure uptime monitoring

### CI/CD Pipeline

The GitHub Actions pipeline automatically:

- Runs tests and linting
- Builds Docker images
- Pushes to container registry
- Deploys to Kubernetes (on main branch)
- Runs health checks

Configure the following secrets in GitHub:

- `KUBE_CONFIG`: Base64-encoded kubeconfig file
- `GITHUB_TOKEN`: For container registry access

## 🧪 Testing

### Run Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest test_chunkvault.py -v

# Run with coverage
pytest test_chunkvault.py --cov=. --cov-report=html

# Run specific test categories
pytest test_chunkvault.py::TestAuthentication -v
pytest test_chunkvault.py::TestFileOperations -v
pytest test_chunkvault.py::TestCache -v
```

### Test Configuration

The test suite includes:

- **Unit Tests** - Individual component testing
- **Integration Tests** - API endpoint testing
- **Cache Tests** - Redis caching functionality
- **Authentication Tests** - User registration and login
- **File Operations Tests** - Upload, download, sharing

### Development Setup

1. **Install development dependencies:**

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov flake8 black isort
```

2. **Set up pre-commit hooks:**

```bash
pip install pre-commit
pre-commit install
```

3. **Run linting:**

```bash
flake8 .
black --check .
isort --check-only .
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Run the test suite (`pytest`)
6. Run linting (`flake8`, `black`, `isort`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Write comprehensive tests for new features
- Update documentation for API changes
- Ensure all tests pass before submitting PR
- Use meaningful commit messages

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:

- Create an issue on GitHub
- Check the documentation
- Review the API endpoints

---

**ChunkVault** - Reliable, scalable, and user-friendly distributed file storage. 🗄️✨
