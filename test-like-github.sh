#!/bin/bash
# test-like-github.sh
# Replicates GitHub Actions test environment locally
# Usage: ./test-like-github.sh [backend|frontend|all]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default to running all tests
TARGET="${1:-all}"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}  Local GitHub Actions Test Environment${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Function to print section headers
section() {
    echo ""
    echo -e "${BLUE}▶ $1${NC}"
    echo -e "${BLUE}$(printf '%.0s─' {1..50})${NC}"
}

# Function to print success
success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error
error() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# Function to print warning
warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    error "Docker is not running. Please start Docker Desktop."
fi

# Backend Tests
run_backend_tests() {
    section "Backend Tests"

    # Cleanup any existing services first
    echo "Cleaning up any existing test services..."
    docker stop test-mongodb test-redis 2>/dev/null || true
    docker network rm test-network 2>/dev/null || true

    # Start MongoDB and Redis services
    echo "Starting MongoDB 7.0 and Redis 7-alpine..."
    docker network create test-network || error "Failed to create Docker network"

    # Start MongoDB
    docker run -d --rm \
        --name test-mongodb \
        --network test-network \
        --health-cmd "mongosh --eval 'db.adminCommand(\"ping\")'" \
        --health-interval 10s \
        --health-timeout 5s \
        --health-retries 5 \
        mongo:7.0 > /dev/null || { cleanup_services; error "Failed to start MongoDB"; }

    # Start Redis
    docker run -d --rm \
        --name test-redis \
        --network test-network \
        --health-cmd "redis-cli ping" \
        --health-interval 10s \
        --health-timeout 5s \
        --health-retries 5 \
        redis:7-alpine > /dev/null || { cleanup_services; error "Failed to start Redis"; }

    # Wait for services to be healthy
    echo "Waiting for services to be healthy..."
    sleep 10

    # Verify services are running
    if ! docker ps | grep -q test-mongodb; then
        cleanup_services
        error "MongoDB failed to start"
    fi
    if ! docker ps | grep -q test-redis; then
        cleanup_services
        error "Redis failed to start"
    fi

    success "Services started successfully"

    # Run backend lint
    section "Backend Lint (Ruff)"
    docker run --rm \
        -v "$(pwd)/backend:/app" \
        -w /app \
        python:3.11 \
        sh -c "
            pip install --quiet --upgrade pip && \
            pip install --quiet 'ruff>=0.8.0' && \
            echo 'Running ruff check...' && \
            ruff check . && \
            echo 'Running ruff format check...' && \
            ruff format --check .
        " || { cleanup_services; error "Backend lint failed"; }

    success "Backend lint passed"

    # Run backend security audit
    section "Backend Security (pip-audit)"
    docker run --rm \
        -v "$(pwd)/backend:/app" \
        -w /app \
        -e PIP_NO_BUILD_ISOLATION=1 \
        python:3.11 \
        sh -c "
            pip install --quiet --upgrade pip 'setuptools<82' wheel Cython && \
            pip install --quiet --no-build-isolation -r requirements.txt && \
            pip install --quiet 'pip-audit>=2.7.0' && \
            pip-audit --strict
        " || warning "Backend security audit failed (non-blocking)"

    success "Backend security passed (or non-blocking failure)"

    # Run backend tests
    section "Backend Tests (pytest)"
    docker run --rm \
        -v "$(pwd)/backend:/app" \
        -w /app \
        --network test-network \
        -e MONGODB_URI=mongodb://test-mongodb:27017 \
        -e REDIS_HOST=test-redis \
        -e REDIS_PORT=6379 \
        -e API_KEY=test-api-key-for-ci \
        -e JWT_SECRET_KEY=test-secret-key-for-ci \
        -e PASSWORD_SALT=test-salt-for-ci \
        -e AUTH_PROVIDER=none \
        -e ENVIRONMENT=testing \
        -e PIP_NO_BUILD_ISOLATION=1 \
        python:3.11 \
        sh -c "
            pip install --quiet --upgrade pip 'setuptools<82' wheel Cython && \
            pip install --quiet --no-build-isolation -r requirements.txt && \
            pip install --quiet --no-build-isolation -r tests/requirements.txt && \
            echo 'Skipping integration tests for faster feedback' && \
            pytest tests/ -v --tb=short --ignore=tests/integration
        " || { cleanup_services; error "Backend tests failed"; }

    success "Backend tests passed"

    cleanup_services
}

# Frontend Tests
run_frontend_tests() {
    section "Frontend Tests"

    # Run frontend lint
    section "Frontend Lint (ESLint)"
    docker run --rm \
        -v "$(pwd)/frontend:/app" \
        -w /app \
        oven/bun:latest \
        sh -c "
            bun install && \
            bun run lint:check
        " || error "Frontend lint failed"

    success "Frontend lint passed"

    # Run frontend type check
    section "Frontend Type Check (TypeScript)"
    docker run --rm \
        -v "$(pwd)/frontend:/app" \
        -w /app \
        oven/bun:latest \
        sh -c "
            bun install && \
            bun run type-check
        " || error "Frontend type check failed"

    success "Frontend type check passed"

    # Run frontend tests
    section "Frontend Tests (Vitest)"
    docker run --rm \
        -v "$(pwd)/frontend:/app" \
        -w /app \
        oven/bun:latest \
        sh -c "
            bun install && \
            bun run test:run
        " || error "Frontend tests failed"

    success "Frontend tests passed"
}

# Cleanup services
cleanup_services() {
    echo ""
    echo "Cleaning up services..."
    docker stop test-mongodb test-redis 2>/dev/null || true
    docker network rm test-network 2>/dev/null || true
}

# Trap cleanup on exit
trap cleanup_services EXIT

# Run tests based on target
case "$TARGET" in
    backend)
        run_backend_tests
        ;;
    frontend)
        run_frontend_tests
        ;;
    all)
        run_backend_tests
        run_frontend_tests
        ;;
    *)
        error "Invalid target: $TARGET. Use 'backend', 'frontend', or 'all'"
        ;;
esac

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  All tests passed! ✓${NC}"
echo -e "${GREEN}================================================${NC}"
