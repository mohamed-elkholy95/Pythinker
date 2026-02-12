# Local GitHub Actions Testing

This guide explains how to run the exact same tests locally that GitHub Actions runs in CI, ensuring your changes will pass before pushing.

## Quick Start

```bash
# Run all tests (backend + frontend)
./test-like-github.sh

# Run only backend tests
./test-like-github.sh backend

# Run only frontend tests
./test-like-github.sh frontend
```

## What It Does

The `test-like-github.sh` script replicates the exact GitHub Actions environment:

### Backend Tests
1. **Starts Services** (in Docker):
   - MongoDB 7.0 (port 27017)
   - Redis 7-alpine (port 6379)

2. **Runs Tests** (in Python 3.11 container):
   - Ruff linter (`ruff check .`)
   - Ruff formatter check (`ruff format --check .`)
   - pip-audit security scan
   - pytest unit tests (excluding integration tests)

3. **Environment Variables** (matches CI):
   ```bash
   MONGODB_URI=mongodb://test-mongodb:27017
   REDIS_HOST=test-redis
   REDIS_PORT=6379
   API_KEY=test-api-key-for-ci
   JWT_SECRET_KEY=test-secret-key-for-ci
   PASSWORD_SALT=test-salt-for-ci
   AUTH_PROVIDER=none
   ENVIRONMENT=testing
   ```

### Frontend Tests
1. **Runs Tests** (in Bun container):
   - ESLint linter (`bun run lint:check`)
   - TypeScript type check (`bun run type-check`)
   - Vitest unit tests (`bun run test:run`)

## Requirements

- Docker Desktop must be running
- No other services using ports 27017 (MongoDB) or 6379 (Redis)

## Troubleshooting

### Port Already in Use
If you get "port already allocated" errors:

```bash
# Stop any running containers
docker stop test-mongodb test-redis

# Or stop all Docker containers
docker stop $(docker ps -q)
```

### Services Not Starting
Check Docker is running and has enough resources:

```bash
# Check Docker status
docker info

# Check running containers
docker ps
```

### Tests Failing Locally
If tests fail locally but pass in CI:

1. **Check Python version**: CI uses Python 3.11
   ```bash
   docker run --rm python:3.11-slim python --version
   ```

2. **Check service versions**:
   - MongoDB: 7.0
   - Redis: 7-alpine
   - Bun: latest

3. **Clean Docker cache**:
   ```bash
   docker system prune -a
   ```

## Comparison with GitHub Actions

| Component | GitHub Actions | Local Script |
|-----------|---------------|--------------|
| Python | 3.11 (via setup-python@v5) | 3.11 (python:3.11-slim) |
| MongoDB | 7.0 (service container) | 7.0 (docker container) |
| Redis | 7-alpine (service container) | 7-alpine (docker container) |
| Bun | latest (via setup-bun@v2) | latest (oven/bun:latest) |
| Network | GitHub Actions services | Docker network |
| Cleanup | Automatic | Automatic (trap on exit) |

## Pre-Push Checklist

Before pushing to GitHub, run locally:

```bash
# 1. Run all tests
./test-like-github.sh

# 2. Check git status
git status

# 3. Review changes
git diff

# 4. Commit and push
git add .
git commit -m "your message"
git push origin main
```

## Manual Testing (Alternative)

If you prefer to run tests manually without Docker:

### Backend
```bash
cd backend

# Start services (via Docker Compose or local install)
# MongoDB on port 27017
# Redis on port 6379

# Set environment variables
export MONGODB_URI=mongodb://localhost:27017
export REDIS_HOST=localhost
export REDIS_PORT=6379
export API_KEY=test-api-key-for-ci
export JWT_SECRET_KEY=test-secret-key-for-ci
export PASSWORD_SALT=test-salt-for-ci
export AUTH_PROVIDER=none
export ENVIRONMENT=testing

# Run tests (requires conda environment)
conda activate pythinker
ruff check .
ruff format --check .
pip-audit --strict
pytest tests/ -v --tb=short --ignore=tests/integration
```

### Frontend
```bash
cd frontend

# Run tests (requires bun)
bun install
bun run lint:check
bun run type-check
bun run test:run
```

## CI Workflow File

The full GitHub Actions workflow is defined in:
- `.github/workflows/test-and-lint.yml`

Any changes to that file should be reflected in `test-like-github.sh`.

## Tips

1. **Run specific backend tests**:
   ```bash
   # After starting services with the script, you can run:
   docker run --rm -it \
     -v "$(pwd)/backend:/app" \
     -w /app \
     --network test-network \
     -e MONGODB_URI=mongodb://test-mongodb:27017 \
     python:3.11-slim bash

   # Then inside container:
   pip install -r requirements.txt
   pip install -r tests/requirements.txt
   pytest tests/specific_test.py -v
   ```

2. **Keep services running**:
   ```bash
   # Start services manually (don't use the script)
   docker run -d --name test-mongodb -p 27017:27017 mongo:7.0
   docker run -d --name test-redis -p 6379:6379 redis:7-alpine

   # Run tests multiple times
   # ...

   # Stop when done
   docker stop test-mongodb test-redis
   docker rm test-mongodb test-redis
   ```

3. **Fast feedback loop**:
   ```bash
   # Run only backend lint (fastest)
   docker run --rm -v "$(pwd)/backend:/app" -w /app python:3.11-slim \
     sh -c "pip install -q ruff && ruff check . && ruff format --check ."
   ```
