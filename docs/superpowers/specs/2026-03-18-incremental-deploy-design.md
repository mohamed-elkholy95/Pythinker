# Production Deployment via Dokploy + Pre-Built GHCR Images

**Date:** 2026-03-18
**Status:** Implemented
**Author:** Mohamed Elkholy

## Architecture

```
git push main
  → GitHub Actions CI: path-filter detects changed services
  → Build ONLY changed images → push to ghcr.io (3-5 min)
  → Dokploy: manual Deploy button pulls pre-built images (~10 sec)
  → Traefik routes pythinker.com → frontend container (port 80)
```

**Key decision:** Dokploy owns deployment and Traefik routing. CI only builds images. No SSH deploy step — Dokploy handles `docker compose pull + up -d`.

## How It Works

### CI Pipeline (`.github/workflows/deploy.yml`)

Triggers on push to `main`. Builds only changed services:

| Path Filter | Service | Image |
|-------------|---------|-------|
| `backend/**` | backend | `ghcr.io/mohamed-elkholy95/pythinker-backend` |
| `frontend/**` | frontend | `ghcr.io/mohamed-elkholy95/pythinker-frontend` |
| `sandbox/**` | sandbox | `ghcr.io/mohamed-elkholy95/pythinker-sandbox` |

Tags: `latest` + `sha-<short-hash>` on every push.

GitHub Secrets (configured):
- `VPS_SSH_KEY` — ed25519 deploy key (`~/.ssh/pythinker_deploy`)
- `VPS_HOST` — `72.60.164.225`
- `VPS_USER` — `root`

### Dokploy Configuration

| Setting | Value |
|---------|-------|
| **Compose Path** | `docker-compose-deploy.yml` |
| **Autodeploy** | OFF (manual deploy only) |
| **Domain** | `pythinker.com` |
| **Domain Port** | `80` (Nginx container port, NOT host port 5174) |
| **Provider** | GitHub → `mohamed-elkholy95/Pythinker` |

**Deploy flow:** Click Deploy → Dokploy clones repo → runs `docker compose -f docker-compose-deploy.yml up -d` → pulls GHCR images → starts containers → Traefik auto-routes via Docker labels.

### Compose File (`docker-compose-deploy.yml`)

Uses pre-built GHCR images (no `build:` directives):

| Service | Image | Internal Port |
|---------|-------|---------------|
| frontend | `ghcr.io/.../pythinker-frontend:latest` | 80 (Nginx) |
| backend | `ghcr.io/.../pythinker-backend:latest` | 8000 |
| gateway | `ghcr.io/.../pythinker-backend:latest` | (shares backend image) |
| sandbox | `ghcr.io/.../pythinker-sandbox:latest` | 8080 |
| mongodb | `mongo:7.0.28` | 27017 |
| redis | `redis:8.4-alpine` | 6379 |
| qdrant | `qdrant/qdrant:v1.16.3` | 6333/6334 |
| minio | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | 9000/9001 |

**Networks:**
- `pythinker-network` (external: true) — inter-service communication
- `dokploy-network` (external: true) — Traefik routing (frontend only)

**Volumes:** All `external: true` with explicit names (e.g., `pythinker-mongodb-data`). Pre-created by Dokploy's initial deploy.

### Traefik Routing

Dokploy injects Docker labels on the frontend container:
```
traefik.http.services.*.loadbalancer.server.port=80
traefik.http.routers.*.rule=Host(`pythinker.com`)
traefik.http.routers.*.tls.certresolver=letsencrypt
traefik.docker.network=dokploy-network
```

**Critical:** The Domain Port in Dokploy MUST be `80` (container port), not `5174` (host port). Traefik connects to containers directly on the Docker network, not through host port mappings.

## Deployment Workflow

### Routine Deploy (after code push)

1. Push code to `main`
2. CI builds changed images automatically (3-5 min)
3. Go to Dokploy → Pythinker → click **Deploy**
4. Dokploy pulls latest images from GHCR and restarts containers (~10 sec)
5. Traefik auto-routes — site is live

### Rollback

```bash
# On VPS — pin to a specific commit SHA
cd /etc/dokploy/compose/pythinker-pythinker-akwnya/code
IMAGE_TAG=sha-abc1234 docker compose -f docker-compose-deploy.yml pull
IMAGE_TAG=sha-abc1234 docker compose -f docker-compose-deploy.yml up -d
```

### Force Rebuild All Images

```bash
gh workflow run "Build & Deploy" --repo mohamed-elkholy95/Pythinker --ref main -f force_build_all=true
```

## Prerequisites (Already Configured)

- [x] GitHub Secrets: `VPS_SSH_KEY`, `VPS_HOST`, `VPS_USER`
- [x] GitHub Environment: `production`
- [x] GHCR packages: public (no auth needed for pull)
- [x] VPS: Docker logged into ghcr.io
- [x] Dokploy: Compose Path = `docker-compose-deploy.yml`
- [x] Dokploy: Autodeploy = OFF
- [x] Dokploy: Domain port = `80`
- [x] Networks: `pythinker-network` and `dokploy-network` exist on VPS
- [x] Volumes: Pre-created with `pythinker-*` names

## Lessons Learned (2026-03-18 Incident)

### 1. Sandbox Supervisor Password Mismatch (FIXED — `sandbox/app/core/config.py`)

**Root cause:** Pydantic `@model_validator` replaced `"supervisor-dev-password"` with a random token. Supervisord (parent process) had already read the original env var → 401 Unauthorized → FATAL crash.

**Fix:** Validator now respects the env var as-is. Three branches: env var set → use it; empty → generate + export; `.env` file only → sync to `os.environ`.

### 2. Container Name Conflict (FIXED — `docker-compose-deploy.yml`)

**Root cause:** `container_name: pythinker-qdrant` conflicted with Dokploy's containers.

**Fix:** Removed all `container_name:` directives. Services use Docker DNS via compose service names.

### 3. Traefik Port Mismatch

**Root cause:** Dokploy read `ports: "5174:80"` and used `5174` as the Traefik backend port. But the container listens on `80` internally. Traefik connected to wrong port → 502 Bad Gateway.

**Fix:** Set Domain Port to `80` in Dokploy Domains tab. Traefik labels now correctly point to the container's internal Nginx port.

### 4. Frontend Planning Panel Covering Screencast (FIXED — `ChatPage.vue`)

**Root cause:** Idle wait beacons (`wait_stage: "execution_wait"`) triggered the planning scaffold overlay, covering the live screencast during agent execution.

**Fix:** `updatePlanProgressPresentation()` now skips events with `wait_stage` set, preserving screencast visibility during tool execution.

## Files Changed

| File | Change |
|------|--------|
| `docker-compose-deploy.yml` | GHCR images, dokploy-network, external volumes, curl healthcheck |
| `.github/workflows/deploy.yml` | GHCR auth, sandbox health check, deploy_config filter |
| `sandbox/app/core/config.py` | Supervisor password sync fix |
| `frontend/src/pages/ChatPage.vue` | Skip idle beacons in planning presentation |
