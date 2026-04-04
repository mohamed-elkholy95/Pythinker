# Production Deployment Guide

## Architecture Overview

The production stack runs all Pythinker services behind a **Traefik v3 reverse proxy** with automatic HTTPS (Let's Encrypt). Key differences from development:

- **Traefik** terminates TLS and load-balances across backend replicas with sticky sessions (required for SSE connections).
- **Backend** runs with **2 replicas** for availability. Traefik distributes requests and pins SSE clients via a session cookie.
- **MongoDB** runs as a **single-node replica set** (`rs0`). The healthcheck auto-initializes the replica set on first boot, enabling oplog and change stream support without manual intervention.
- **Redis** is **password-protected** (`--requirepass`). All clients connect via `redis://:PASSWORD@redis:6379/0`.
- **Qdrant** exposes both REST (6333) and gRPC (6334) internally. An optional API key can be set.
- **MinIO** credentials are injected from environment variables. No ports are exposed to the host; backend accesses MinIO over the internal network.
- **Sandbox** ports are not exposed to the host. The backend reaches the sandbox over the `pythinker-prod` network.
- All services share a single `pythinker-prod` bridge network. No ports are published to the host except Traefik's 80/443.

## Required Environment Variables

Create a `.env.production` file in the project root. All variables below are required unless marked optional.

```bash
# --- Domain & TLS ---
DOMAIN=pythinker.example.com        # Your production domain
ACME_EMAIL=admin@example.com        # Let's Encrypt notification email

# --- Images ---
IMAGE_REGISTRY=pythinker             # Docker registry prefix
IMAGE_TAG=latest                     # Image tag (pin to a SHA or semver in CI)

# --- Secrets ---
SANDBOX_API_SECRET=<generate-random-32-char>
REDIS_PASSWORD=<generate-random-32-char>
MINIO_ROOT_USER=<minio-admin-user>
MINIO_ROOT_PASSWORD=<generate-random-32-char>

# --- Optional ---
QDRANT_API_KEY=                      # Leave empty to disable Qdrant auth
REDIS_MAXMEMORY=1gb                  # Default: 1gb
REDIS_MAXMEMORY_POLICY=volatile-lfu  # Default: volatile-lfu
SANDBOX_LIFECYCLE_MODE=static        # static | dynamic
SANDBOX_ADDRESS=sandbox              # Hostname of sandbox service
FAST_MODEL=qwen/qwen3-coder-next
ENABLE_SANDBOX_ADDONS=0

# --- LLM / Search API Keys (in .env.production, read by backend) ---
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# SERPER_API_KEY=...
# EMBEDDING_API_KEY=...
```

Generate secrets with:

```bash
openssl rand -hex 32
```

## Deployment Steps

### 1. Prepare the host

Ensure Docker Engine 24+ and Docker Compose v2 are installed. Open ports 80 and 443 in your firewall.

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### 2. Clone and configure

```bash
git clone <repo-url> pythinker && cd pythinker
cp .env.example .env.production
# Edit .env.production with production values (see table above)
```

### 3. Build images

Before deploying, validate the compose files:

```bash
./scripts/validate_compose_configs.sh
```

This runs the same `docker compose ... config --no-interpolate` check used by CI and the VPS bootstrap script, which catches broken service references like the sandbox dependency issue before rollout.

```bash
docker compose -f docker-compose-production.yml build
```

Or pull pre-built images if using a registry:

```bash
docker compose -f docker-compose-production.yml pull
```

### 4. Start the stack

```bash
docker compose -f docker-compose-production.yml --env-file .env.production up -d
```

### 5. Verify

```bash
# Check all services are healthy
docker compose -f docker-compose-production.yml ps

# Verify MongoDB replica set initialized
docker compose -f docker-compose-production.yml exec mongodb mongosh --eval "rs.status()"

# Verify Redis auth
docker compose -f docker-compose-production.yml exec redis redis-cli -a "$REDIS_PASSWORD" ping

# Verify backend health
curl -s https://pythinker.example.com/api/v1/health
```

### 6. View logs

```bash
# All services
docker compose -f docker-compose-production.yml logs -f

# Single service
docker compose -f docker-compose-production.yml logs -f backend
```

## Updating

```bash
docker compose -f docker-compose-production.yml pull   # or build
docker compose -f docker-compose-production.yml --env-file .env.production up -d
```

Docker Compose performs rolling updates for replicated services. Backend replicas are replaced one at a time when the new container passes its healthcheck.

## Backup

### MongoDB

```bash
docker compose -f docker-compose-production.yml exec mongodb \
  mongodump --archive --gzip > backup-$(date +%F).gz
```

### Redis

Redis persists via AOF in the `pythinker-prod-redis-data` volume. For a point-in-time snapshot:

```bash
docker compose -f docker-compose-production.yml exec redis \
  redis-cli -a "$REDIS_PASSWORD" BGSAVE
```

### Qdrant

Qdrant snapshots can be triggered via its REST API:

```bash
curl -X POST http://localhost:6333/collections/user_knowledge/snapshots
```

### MinIO

Use `mc` (MinIO Client) to mirror data to an offsite location.
