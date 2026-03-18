# Incremental Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace full-rebuild deploys with pre-built ghcr.io images + smart CI, so only changed services rebuild and VPS deploys take seconds.

**Architecture:** GitHub Actions builds images on push to `main` with path filtering (only changed services). A deploy job SSHs to the VPS and runs `docker compose pull + up -d` from a dedicated `/opt/pythinker-deploy/` directory. Dokploy's auto-deploy is disabled; it remains for monitoring only.

**Tech Stack:** Docker Compose, GitHub Actions, ghcr.io, SSH deploy, dorny/paths-filter

**Spec:** `docs/superpowers/specs/2026-03-18-incremental-deploy-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `docker-compose-deploy.yml` | Create | Production compose with `image:` refs, no build directives |
| `.github/workflows/deploy.yml` | Create | Build changed images + SSH deploy to VPS |
| `.github/workflows/docker-build-and-push.yml` | Unchanged | Keep for version-tag releases only |

**Design decision:** Separate CI workflow (`deploy.yml`) for main-branch deploys rather than modifying the existing tag-based workflow. This keeps release builds and continuous deploys independent — different triggers, different tagging, different post-build actions. The existing `docker-build-and-push.yml` stays untouched for semver releases.

---

## Task 1: Create `docker-compose-deploy.yml`

**Files:**
- Create: `docker-compose-deploy.yml`

This is the core deliverable — a production compose file that uses pre-built images instead of `build:` directives.

- [ ] **Step 1: Create the deploy compose file**

The file mirrors `docker-compose.yml` but with these changes:
- `build:` → `image:` for frontend, backend, gateway, sandbox
- Remove all `develop.watch` blocks
- Remove `command: ["./dev.sh"]` on backend (use default `run.sh` from image)
- Remove `BACKEND_ENABLE_RELOAD` and `BACKEND_UVICORN_GRACEFUL_TIMEOUT` env vars from backend
- Remove `UVI_ARGS="--reload"` and `FRAMEWORK_UVI_ARGS="--reload"` from sandbox
- Change `LOG_LEVEL` default from `DEBUG` to `INFO` on sandbox
- Frontend: map port `5174:80` (Nginx on port 80 inside, host port 5174 to match current setup)
- Frontend: set `BACKEND_URL=http://backend:8000` for nginx proxy_pass
- Keep all infrastructure services (mongodb, redis, minio, minio-init, qdrant) identical
- Keep all volumes and networks identical
- Sandbox `seccomp` path: relative `./sandbox/seccomp-sandbox.hardened.json` (resolves correctly since compose runs from `/opt/pythinker-deploy/`)

```yaml
# =============================================================================
# Pythinker — Deploy Compose (Pre-built images from ghcr.io)
#
# Usage:
#   docker compose -f docker-compose-deploy.yml pull
#   docker compose -f docker-compose-deploy.yml up -d
#
# Images are built by CI (.github/workflows/deploy.yml) and pushed to ghcr.io.
# This file is used on the VPS at /opt/pythinker-deploy/.
#
# Configuration:
#   IMAGE_TAG=latest          (default) — latest main branch build
#   IMAGE_TAG=sha-abc1234     — pin to specific commit
# =============================================================================

services:
  # ---------------------------------------------------------------------------
  # Frontend (Nginx serving Vue 3 SPA)
  # ---------------------------------------------------------------------------
  frontend:
    image: ghcr.io/mohamed-elkholy95/pythinker-frontend:${IMAGE_TAG:-latest}
    ports:
      - "5174:80"
    environment:
      - BACKEND_URL=http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - pythinker-network
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://localhost:80/ || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  # ---------------------------------------------------------------------------
  # Backend (FastAPI + uvicorn production)
  # ---------------------------------------------------------------------------
  backend:
    image: ghcr.io/mohamed-elkholy95/pythinker-backend:${IMAGE_TAG:-latest}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - dspy_cache:/app/data/dspy_cache
    ports:
      - "8000:8000"
    depends_on:
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      minio:
        condition: service_healthy
      sandbox:
        condition: service_started
    restart: unless-stopped
    networks:
      - pythinker-network
    env_file:
      - .env
    environment:
      - SANDBOX_LIFECYCLE_MODE=static
      - SANDBOX_ADDRESS=sandbox
      - SANDBOX_IMAGE=pythinker/pythinker-sandbox
      - MONGODB_URI=${MONGODB_URI:-mongodb://mongodb:27017/pythinker?authSource=admin}
      - MONGODB_USERNAME=${MONGODB_USERNAME:-pythinker_admin}
      - MONGODB_PASSWORD=${MONGODB_PASSWORD:-pythinker_admin_password_change_me}
      - SANDBOX_CHROME_ARGS=--no-sandbox --disable-setuid-sandbox --disable-crashpad --user-data-dir=/tmp/chrome --no-zygote --js-flags=--max-old-space-size=512
      - SANDBOX_API_SECRET=${SANDBOX_API_SECRET:-dev-sandbox-secret-change-me}
      - LOCAL_AUTH_PASSWORD=${LOCAL_AUTH_PASSWORD:-changeme}
      - GRPC_ENABLE_FORK_SUPPORT=0
      - NODE_OPTIONS=--no-deprecation
      - SANDBOX_CALLBACK_TOKEN=${SANDBOX_CALLBACK_TOKEN:-}
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8000/api/v1/health >/dev/null || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s

  # ---------------------------------------------------------------------------
  # Gateway (Telegram / channel integration)
  # ---------------------------------------------------------------------------
  gateway:
    image: ghcr.io/mohamed-elkholy95/pythinker-backend:${IMAGE_TAG:-latest}
    command: ["python", "-m", "app.interfaces.gateway.gateway_runner"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - dspy_cache:/app/data/dspy_cache
    depends_on:
      backend:
        condition: service_healthy
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      minio:
        condition: service_healthy
      sandbox:
        condition: service_started
    restart: unless-stopped
    networks:
      - pythinker-network
    env_file:
      - .env
    environment:
      - CHANNEL_GATEWAY_ENABLED=true
      - SANDBOX_LIFECYCLE_MODE=static
      - SANDBOX_ADDRESS=sandbox
      - SANDBOX_IMAGE=pythinker/pythinker-sandbox
      - MONGODB_URI=${MONGODB_URI:-mongodb://mongodb:27017/pythinker?authSource=admin}
      - MONGODB_USERNAME=${MONGODB_USERNAME:-pythinker_admin}
      - MONGODB_PASSWORD=${MONGODB_PASSWORD:-pythinker_admin_password_change_me}
      - SANDBOX_CHROME_ARGS=--no-sandbox --disable-setuid-sandbox --disable-crashpad --user-data-dir=/tmp/chrome --no-zygote --js-flags=--max-old-space-size=512
      - SANDBOX_API_SECRET=${SANDBOX_API_SECRET:-dev-sandbox-secret-change-me}
      - LOCAL_AUTH_PASSWORD=${LOCAL_AUTH_PASSWORD:-changeme}
      - GRPC_ENABLE_FORK_SUPPORT=0
      - NODE_OPTIONS=--no-deprecation
      - FAST_MODEL=${FAST_MODEL:-}

  # ---------------------------------------------------------------------------
  # Sandbox (Isolated Docker execution environment)
  # ---------------------------------------------------------------------------
  sandbox:
    image: ghcr.io/mohamed-elkholy95/pythinker-sandbox:${IMAGE_TAG:-latest}
    hostname: sandbox
    security_opt:
      - no-new-privileges:true
      - seccomp=./sandbox/seccomp-sandbox.hardened.json
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
      - SYS_ADMIN
    volumes:
      - /app/__pycache__
      - /app/.venv
    ports:
      - "127.0.0.1:8083:8080"
      - "127.0.0.1:8082:8082"
      - "127.0.0.1:8443:8443"
    shm_size: '4gb'
    tmpfs:
      - /run:size=50M,nosuid,nodev,uid=1000,gid=1000
      - /run/user/1000:size=10M,nosuid,nodev,uid=1000,gid=1000,mode=0700
      - /tmp:size=1g,nosuid,nodev
      - /home/ubuntu/.cache:size=150M,nosuid,nodev,uid=1000,gid=1000,mode=0700
    ulimits:
      nofile:
        soft: 65536
        hard: 65536
    deploy:
      resources:
        limits:
          memory: 6G
          cpus: '2'
          pids: 1024
        reservations:
          memory: 1G
    environment:
      - SANDBOX_STREAMING_MODE=${SANDBOX_STREAMING_MODE:-cdp_only}
      - SANDBOX_API_SECRET=${SANDBOX_API_SECRET:-dev-sandbox-secret-change-me}
      - SUPERVISOR_RPC_USERNAME=${SUPERVISOR_RPC_USERNAME:-supervisor}
      - SUPERVISOR_RPC_PASSWORD=${SUPERVISOR_RPC_PASSWORD:-supervisor-dev-password}
      - FRAMEWORK_DATABASE_URL=sqlite+aiosqlite:////home/ubuntu/.local/pythinker_sandbox.db
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - CHROME_ARGS=--no-sandbox --disable-setuid-sandbox --disable-crashpad --user-data-dir=/tmp/chrome --no-zygote --renderer-process-limit=2 --disable-gpu --disable-features=CalculateNativeWinOcclusion --disable-gpu-memory-buffer-compositor-resources --disable-gpu-memory-buffer-video-frames --js-flags=--max-old-space-size=512
      - BROWSER_PATH=/usr/local/bin/chromium
      - LIBGL_ALWAYS_SOFTWARE=1
      - TZ=${TZ:-UTC}
      - SANDBOX_VERSION=${IMAGE_TAG:-latest}
      - SHELL_USE_STRUCTURED_MARKERS=${SHELL_USE_STRUCTURED_MARKERS:-true}
      - RUNTIME_API_HOST=${RUNTIME_API_HOST:-http://backend:8000}
      - RUNTIME_API_TOKEN=${SANDBOX_CALLBACK_TOKEN:-}
      - OPENAI_API_BASE=${SANDBOX_LLM_PROXY_URL:-http://backend:8000/api/v1/llm-proxy/v1}
      - OPENAI_BASE_URL=${SANDBOX_LLM_PROXY_URL:-http://backend:8000/api/v1/llm-proxy/v1}
      - OPENAI_API_KEY=${SANDBOX_LLM_PROXY_KEY:-}
      - CODE_SERVER_PORT=${CODE_SERVER_PORT:-8443}
      - CODE_SERVER_PASSWORD=${CODE_SERVER_PASSWORD:-disabled}
      - ENABLE_CODE_SERVER=${ENABLE_CODE_SERVER:-0}
      - OTEL_ENABLED=${OTEL_ENABLED:-false}
      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-}
      - OTEL_SERVICE_NAME=sandbox-runtime
      - OTEL_TRACES_SAMPLER_RATIO=${OTEL_TRACES_SAMPLER_RATIO:-1.0}
      - SENTRY_DSN=${SANDBOX_SENTRY_DSN:-}
      - GH_TOKEN=${GH_TOKEN:-}
      - GOOGLE_DRIVE_TOKEN=${GOOGLE_DRIVE_TOKEN:-}
      - GOOGLE_WORKSPACE_CLI_TOKEN=${GOOGLE_WORKSPACE_CLI_TOKEN:-}
    restart: unless-stopped
    networks:
      - pythinker-network
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      start_period: 60s
      retries: 3

  # ---------------------------------------------------------------------------
  # MongoDB
  # ---------------------------------------------------------------------------
  mongodb:
    image: mongo:7.0.28
    command: ["mongod", "--wiredTigerCacheSizeGB", "0.25"]
    environment:
      - MONGO_INITDB_ROOT_USERNAME=${MONGODB_USERNAME:-pythinker_admin}
      - MONGO_INITDB_ROOT_PASSWORD=${MONGODB_PASSWORD:-pythinker_admin_password_change_me}
    mem_limit: 512m
    volumes:
      - mongodb_data:/data/db
    restart: unless-stopped
    ports:
      - "127.0.0.1:27017:27017"
    networks:
      - pythinker-network
    healthcheck:
      test: ["CMD-SHELL", "mongosh --norc --quiet -u \"$$MONGO_INITDB_ROOT_USERNAME\" -p \"$$MONGO_INITDB_ROOT_PASSWORD\" --authenticationDatabase admin --eval \"db.runCommand('ping').ok\" || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s

  # ---------------------------------------------------------------------------
  # Redis
  # ---------------------------------------------------------------------------
  redis:
    image: redis:8.4-alpine
    mem_limit: 512m
    command:
      - redis-server
      - --save
      - ""
      - --appendonly
      - "yes"
      - --appendfsync
      - everysec
      - --aof-use-rdb-preamble
      - "yes"
      - --loglevel
      - warning
      - --timeout
      - "0"
      - --maxmemory
      - ${REDIS_MAXMEMORY:-512mb}
      - --maxmemory-policy
      - ${REDIS_MAXMEMORY_POLICY:-volatile-lfu}
      - --lazyfree-lazy-eviction
      - "yes"
      - --latency-monitor-threshold
      - "100"
    volumes:
      - redis_runtime_data:/data
    restart: unless-stopped
    networks:
      - pythinker-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 5s

  # ---------------------------------------------------------------------------
  # MinIO (S3-compatible object storage)
  # ---------------------------------------------------------------------------
  minio:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minio-dev-admin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minio-dev-password-change-me}
      - MINIO_IDENTITY_OPENID_ENABLE=off
    volumes:
      - minio_data:/data
    ports:
      - "127.0.0.1:9010:9000"
      - "127.0.0.1:9011:9001"
    restart: unless-stopped
    networks:
      - pythinker-network
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ---------------------------------------------------------------------------
  # MinIO Init (create service user)
  # ---------------------------------------------------------------------------
  minio-init:
    image: minio/mc:RELEASE.2025-08-13T08-35-41Z
    depends_on:
      minio:
        condition: service_healthy
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minio-dev-admin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minio-dev-password-change-me}
      - MINIO_SERVICE_USER=${MINIO_SERVICE_USER:-pythinker-svc}
      - MINIO_SERVICE_PASSWORD=${MINIO_SERVICE_PASSWORD:-pythinker-svc-secret-change-me}
    entrypoint: /bin/sh
    command:
      - -c
      - |
        sleep 3 && \
        mc alias set myminio http://minio:9000 "$${MINIO_ROOT_USER}" "$${MINIO_ROOT_PASSWORD}" && \
        mc admin user add myminio "$${MINIO_SERVICE_USER}" "$${MINIO_SERVICE_PASSWORD}" 2>/dev/null || true && \
        mc admin policy attach myminio readwrite --user "$${MINIO_SERVICE_USER}" 2>/dev/null || true && \
        echo "MinIO service user '$$MINIO_SERVICE_USER' ready with readwrite policy"
    networks:
      - pythinker-network
    restart: "no"

  # ---------------------------------------------------------------------------
  # Qdrant (Vector database)
  # ---------------------------------------------------------------------------
  qdrant:
    image: qdrant/qdrant:v1.16.3
    container_name: pythinker-qdrant
    mem_limit: 1g
    ports:
      - "127.0.0.1:6333:6333"
      - "127.0.0.1:6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334
    restart: unless-stopped
    networks:
      - pythinker-network
    healthcheck:
      test: ["CMD-SHELL", "bash -c 'echo > /dev/tcp/localhost/6333' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

volumes:
  mongodb_data:
    name: pythinker-mongodb-data
  redis_runtime_data:
    name: pythinker-redis-runtime-data
  qdrant_data:
    name: pythinker-qdrant-data
  minio_data:
    name: pythinker-minio-data
  dspy_cache:
    name: pythinker-dspy-cache

networks:
  pythinker-network:
    name: pythinker-network
    driver: bridge
```

- [ ] **Step 2: Validate compose file syntax**

Run: `docker compose -f docker-compose-deploy.yml config --quiet`
Expected: No output (valid syntax)

- [ ] **Step 3: Commit**

```bash
git add docker-compose-deploy.yml
git commit -m "feat(infra): add deploy compose with pre-built ghcr.io images"
```

---

## Task 2: Create CI Deploy Workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

A new workflow that triggers on push to `main`, builds only changed images, and deploys via SSH.

- [ ] **Step 1: Create the deploy workflow**

```yaml
name: Build & Deploy

on:
  push:
    branches: [main]
    paths-ignore:
      - 'docs/**'
      - '*.md'
      - '.github/workflows/test-and-lint.yml'
      - '.github/workflows/create-release.yml'
      - '.github/workflows/security-scan.yml'
  workflow_dispatch:
    inputs:
      force_build_all:
        description: 'Force build all images (ignore path filter)'
        type: boolean
        default: false
      sandbox_addons:
        description: 'Enable sandbox addons (code-server, etc.)'
        type: boolean
        default: false

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read
  packages: write

env:
  GHCR_REGISTRY: ghcr.io
  IMAGE_PREFIX: ghcr.io/mohamed-elkholy95

jobs:
  # ---------------------------------------------------------------------------
  # Detect which services have file changes
  # ---------------------------------------------------------------------------
  changes:
    runs-on: ubuntu-latest
    outputs:
      backend: ${{ steps.filter.outputs.backend }}
      frontend: ${{ steps.filter.outputs.frontend }}
      sandbox: ${{ steps.filter.outputs.sandbox }}
      any_app: ${{ steps.check.outputs.any_app }}
    steps:
      - uses: actions/checkout@v4

      - name: Detect changed paths
        uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            backend:
              - 'backend/**'
            frontend:
              - 'frontend/**'
            sandbox:
              - 'sandbox/**'

      - name: Check if any app service changed
        id: check
        run: |
          if [ "${{ steps.filter.outputs.backend }}" = "true" ] || \
             [ "${{ steps.filter.outputs.frontend }}" = "true" ] || \
             [ "${{ steps.filter.outputs.sandbox }}" = "true" ] || \
             [ "${{ inputs.force_build_all }}" = "true" ]; then
            echo "any_app=true" >> "$GITHUB_OUTPUT"
          else
            echo "any_app=false" >> "$GITHUB_OUTPUT"
          fi

  # ---------------------------------------------------------------------------
  # Build changed images and push to ghcr.io
  # ---------------------------------------------------------------------------
  build:
    needs: changes
    if: needs.changes.outputs.any_app == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: true
      matrix:
        include:
          - component: backend
            changed: ${{ needs.changes.outputs.backend }}
          - component: frontend
            changed: ${{ needs.changes.outputs.frontend }}
          - component: sandbox
            changed: ${{ needs.changes.outputs.sandbox }}
    steps:
      - name: Skip unchanged component
        if: matrix.changed != 'true' && inputs.force_build_all != true
        run: echo "Skipping ${{ matrix.component }} — no changes detected"

      - name: Checkout code
        if: matrix.changed == 'true' || inputs.force_build_all == true
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        if: matrix.changed == 'true' || inputs.force_build_all == true
        uses: docker/setup-buildx-action@v4

      - name: Log in to ghcr.io
        if: matrix.changed == 'true' || inputs.force_build_all == true
        uses: docker/login-action@v4
        with:
          registry: ${{ env.GHCR_REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        if: matrix.changed == 'true' || inputs.force_build_all == true
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE_PREFIX }}/pythinker-${{ matrix.component }}
          tags: |
            type=raw,value=latest
            type=sha,prefix=sha-,format=short

      - name: Set build date
        if: matrix.changed == 'true' || inputs.force_build_all == true
        id: build_date
        run: echo "date=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" >> "$GITHUB_OUTPUT"

      - name: Build and push
        if: matrix.changed == 'true' || inputs.force_build_all == true
        uses: docker/build-push-action@v5
        with:
          context: ./${{ matrix.component }}
          file: ./${{ matrix.component }}/Dockerfile
          platforms: linux/amd64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          build-args: |
            GIT_VERSION=${{ github.ref_name }}
            GIT_SHA=${{ github.sha }}
            BUILD_DATE=${{ steps.build_date.outputs.date }}
            ENABLE_SANDBOX_ADDONS=${{ inputs.sandbox_addons == true && '1' || '0' }}
          cache-from: type=gha,scope=${{ matrix.component }}
          cache-to: type=gha,scope=${{ matrix.component }},mode=max

  # ---------------------------------------------------------------------------
  # Deploy to VPS via SSH
  # ---------------------------------------------------------------------------
  deploy:
    needs: [changes, build]
    if: always() && (needs.build.result == 'success' || needs.changes.outputs.any_app == 'false')
    runs-on: ubuntu-latest
    timeout-minutes: 5
    environment: production
    steps:
      - name: Skip deploy (no app changes)
        if: needs.changes.outputs.any_app == 'false'
        run: echo "No app changes — skipping deploy"

      - name: Deploy via SSH
        if: needs.changes.outputs.any_app == 'true'
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script_stop: true
          script: |
            set -euo pipefail
            cd /opt/pythinker-deploy

            echo "==> Pulling latest compose file..."
            git pull origin main --ff-only

            echo "==> Pulling updated images..."
            docker compose -f docker-compose-deploy.yml pull

            echo "==> Starting services..."
            docker compose -f docker-compose-deploy.yml up -d --remove-orphans

            echo "==> Waiting for backend health..."
            for i in $(seq 1 30); do
              if curl -fsS http://localhost:8000/api/v1/health >/dev/null 2>&1; then
                echo "Backend healthy!"
                break
              fi
              if [ "$i" -eq 30 ]; then
                echo "ERROR: Backend health check failed after 30 attempts"
                docker compose -f docker-compose-deploy.yml logs --tail 50 backend
                exit 1
              fi
              sleep 2
            done

            echo "==> Cleaning up old images..."
            docker image prune -f

            echo "==> Deploy complete!"
```

- [ ] **Step 2: Validate workflow syntax**

Run: `cd /Users/panda/Desktop/Projects/Pythinker && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "feat(ci): add build-and-deploy workflow with path filtering"
```

---

## Task 3: Add GitHub Secrets

**Files:** None (GitHub settings)

**Must be completed before Task 4** — the CI workflow's deploy job needs these secrets to SSH to the VPS.

- [ ] **Step 1: Generate SSH key for CI deploy**

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f /tmp/deploy-key -N ""
```

- [ ] **Step 2: Add public key to VPS authorized_keys**

```bash
ssh vps "cat >> ~/.ssh/authorized_keys" < /tmp/deploy-key.pub
```

- [ ] **Step 3: Add secrets to GitHub**

```bash
gh secret set VPS_SSH_KEY < /tmp/deploy-key
gh secret set VPS_HOST --body "YOUR_VPS_IP_OR_HOSTNAME"
gh secret set VPS_USER --body "root"
```

- [ ] **Step 4: Clean up local key file**

```bash
rm /tmp/deploy-key /tmp/deploy-key.pub
```

- [ ] **Step 5: Create GitHub environment**

The deploy job uses `environment: production`. Create this in GitHub:

```bash
gh api repos/{owner}/{repo}/environments/production -X PUT
```

---

## Task 4: Set Up VPS Deploy Directory

**Files:** None (VPS commands only)

This task prepares the VPS for the new deployment flow. All commands run via `ssh vps`.

- [ ] **Step 1: Create deploy directory and clone repo**

```bash
ssh vps "mkdir -p /opt/pythinker-deploy && cd /opt/pythinker-deploy && git clone https://github.com/mohamed-elkholy95/Pythinker.git ."
```

Expected: Repository cloned successfully

- [ ] **Step 2: Copy .env from Dokploy-managed directory**

```bash
ssh vps "cp /etc/dokploy/compose/pythinker-pythinker-akwnya/code/.env /opt/pythinker-deploy/.env"
```

Expected: File copied

- [ ] **Step 3: Verify seccomp profile and repo structure**

The sandbox service references `./sandbox/seccomp-sandbox.hardened.json` as a relative path. Since the repo is cloned to `/opt/pythinker-deploy/`, this file is already present from the git clone.

```bash
ssh vps "test -f /opt/pythinker-deploy/sandbox/seccomp-sandbox.hardened.json && echo OK"
```

Expected: `OK`

- [ ] **Step 4: Verify volume names match existing Dokploy-managed volumes**

Before cutting over, confirm the new compose will reuse existing data volumes (not create empty ones):

```bash
ssh vps "docker volume ls --format '{{.Name}}' | grep pythinker"
```

Expected: Should show `pythinker-mongodb-data`, `pythinker-redis-runtime-data`, `pythinker-qdrant-data`, `pythinker-minio-data`, `pythinker-dspy-cache`. These match the named volumes in `docker-compose-deploy.yml`. If names differ, update the compose file before proceeding.

- [ ] **Step 5: Seed initial images by running first build**

Trigger the workflow manually to create the initial `latest` tags on ghcr.io:

```bash
gh workflow run deploy.yml --ref main -f force_build_all=true
```

Wait for it to complete:
```bash
gh run list --workflow=deploy.yml --limit 1
```

Expected: Build jobs succeed, images appear on ghcr.io. The deploy job will fail on this first run because: (1) containers aren't running yet on VPS, and (2) `git pull` in the deploy dir may not be ready. That's OK — the images are pushed. We'll start containers manually in Step 7.

- [ ] **Step 6: Disable Dokploy auto-deploy and stop old containers**

First, disable Dokploy auto-deploy for the Pythinker project in the Dokploy dashboard (Settings → Auto Deploy → Off).

Then stop old containers:
```bash
ssh vps "cd /etc/dokploy/compose/pythinker-pythinker-akwnya/code && docker compose down"
```

Expected: All pythinker containers stop. Volumes persist (not using `-v`).

**Warning:** Never commit directly in `/opt/pythinker-deploy/` — `git pull --ff-only` will fail if local commits exist. This directory is CI-managed only.

- [ ] **Step 7: Start containers from new deploy directory**

```bash
ssh vps "cd /opt/pythinker-deploy && docker compose -f docker-compose-deploy.yml pull && docker compose -f docker-compose-deploy.yml up -d"
```

Expected: All services start using pre-built images

- [ ] **Step 8: Verify all services are healthy**

```bash
ssh vps "docker compose -f /opt/pythinker-deploy/docker-compose-deploy.yml ps"
```

Expected: All services show `Up` / `healthy`

```bash
ssh vps "curl -fsS http://localhost:8000/api/v1/health"
```

Expected: Health check response

---

## Task 5: End-to-End Verification

- [ ] **Step 1: Make a small backend change and push**

Edit a comment or log message in `backend/app/main.py`, commit, and push to `main`.

- [ ] **Step 2: Verify CI only builds backend**

```bash
gh run list --workflow=deploy.yml --limit 1
gh run view <run-id> --log | grep -E "(Skipping|Build and push)"
```

Expected: Frontend and sandbox show "Skipping — no changes detected". Backend builds and pushes.

- [ ] **Step 3: Verify deploy succeeds**

Check the deploy job logs:
```bash
gh run view <run-id> --job deploy
```

Expected: `Backend healthy!` and `Deploy complete!` in logs.

- [ ] **Step 4: Verify the app works**

Open `https://pythinker.com` in browser and test basic functionality.

- [ ] **Step 5: Commit deploy compose file to repo**

The compose file was committed in Task 1. Verify it's on `main`:
```bash
git log --oneline -5
```
