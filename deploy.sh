#!/bin/bash

# ChunkVault Deployment Script
# This script helps deploy ChunkVault in different environments

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    if ! command_exists docker; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command_exists docker-compose; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Function to deploy with Docker Compose
deploy_docker_compose() {
    print_status "Deploying ChunkVault with Docker Compose..."
    
    # Build images
    print_status "Building Docker images..."
    docker-compose build
    
    # Start services
    print_status "Starting services..."
    docker-compose up -d
    
    # Wait for services to be ready
    print_status "Waiting for services to be ready..."
    sleep 30
    
    # Check service health
    print_status "Checking service health..."
    docker-compose ps
    
    print_success "ChunkVault deployed successfully with Docker Compose!"
    print_status "Access the application at:"
    echo "  - Web UI: http://localhost:8501"
    echo "  - API: http://localhost:8000"
    echo "  - Prometheus: http://localhost:9090"
    echo "  - Grafana: http://localhost:3000 (admin/admin)"
}

# Function to deploy to Kubernetes
deploy_kubernetes() {
    print_status "Deploying ChunkVault to Kubernetes..."
    
    if ! command_exists kubectl; then
        print_error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi
    
    # Check if kubectl is configured
    if ! kubectl cluster-info >/dev/null 2>&1; then
        print_error "kubectl is not configured or cluster is not accessible."
        exit 1
    fi
    
    # Create namespace
    print_status "Creating namespace..."
    kubectl apply -f k8s/infrastructure/namespace.yaml
    
    # Deploy infrastructure
    print_status "Deploying infrastructure..."
    kubectl apply -f k8s/infrastructure/postgres.yaml
    kubectl apply -f k8s/infrastructure/redis.yaml
    
    # Wait for infrastructure to be ready
    print_status "Waiting for infrastructure to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/postgres -n chunkvault
    kubectl wait --for=condition=available --timeout=300s deployment/redis -n chunkvault
    
    # Deploy storage nodes
    print_status "Deploying storage nodes..."
    kubectl apply -f k8s/storage/storage-nodes.yaml
    
    # Deploy API and workers
    print_status "Deploying API and workers..."
    kubectl apply -f k8s/api/api-deployment.yaml
    kubectl apply -f k8s/api/celery.yaml
    kubectl apply -f k8s/api/ui.yaml
    
    # Deploy monitoring
    print_status "Deploying monitoring..."
    kubectl apply -f k8s/monitoring/prometheus.yaml
    kubectl apply -f k8s/monitoring/grafana.yaml
    
    # Wait for deployments to be ready
    print_status "Waiting for deployments to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/chunkvault-api -n chunkvault
    kubectl wait --for=condition=available --timeout=300s deployment/chunkvault-ui -n chunkvault
    
    # Show deployment status
    print_status "Deployment status:"
    kubectl get pods -n chunkvault
    kubectl get services -n chunkvault
    
    print_success "ChunkVault deployed successfully to Kubernetes!"
    print_status "To access the services, use port forwarding:"
    echo "  kubectl port-forward -n chunkvault svc/chunkvault-ui 8501:8501"
    echo "  kubectl port-forward -n chunkvault svc/grafana 3000:3000"
    echo "  kubectl port-forward -n chunkvault svc/prometheus 9090:9090"
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    
    if ! command_exists python3; then
        print_error "Python 3 is not installed. Please install Python 3 first."
        exit 1
    fi
    
    # Install test dependencies
    print_status "Installing test dependencies..."
    pip install pytest pytest-asyncio pytest-cov
    
    # Run tests
    print_status "Running test suite..."
    pytest test_chunkvault.py -v
    
    print_success "Tests completed successfully!"
}

# Function to show help
show_help() {
    echo "ChunkVault Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  docker-compose    Deploy with Docker Compose (development)"
    echo "  kubernetes        Deploy to Kubernetes (production)"
    echo "  test              Run test suite"
    echo "  help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 docker-compose"
    echo "  $0 kubernetes"
    echo "  $0 test"
}

# Main script logic
main() {
    case "${1:-help}" in
        "docker-compose")
            check_prerequisites
            deploy_docker_compose
            ;;
        "kubernetes")
            check_prerequisites
            deploy_kubernetes
            ;;
        "test")
            run_tests
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            print_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
