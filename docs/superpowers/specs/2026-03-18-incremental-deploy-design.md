# Incremental Deployment via Pre-Built Images

**Date:** 2026-03-18
**Status:** Approved
**Author:** Mohamed Elkholy

## Problem

Every push to `main` triggers a full redeploy on the VPS via Dokploy. Dokploy clones the repo and runs `docker compose up --build` using `docker-compose.yml`, which:

1. Rebuilds **all 4 app images** from source (~8GB total: backend 2GB, frontend 1GB, sandbox 2.8GB, gateway 2GB)
2. Applies **development-level compose configurations** in production — `develop.watch` blocks, `BACKEND_ENABLE_RELOAD=1` env var, dev-tuned healthcheck intervals, and `Dockerfile.dev` for frontend (Vite dev server instead of Nginx)
3. Takes significant time and CPU on a 4-core/16GB VPS that also runs other services

**Note:** The backend and sandbox images are built from their production `Dockerfile` (multi-stage), so the built images themselves are production-grade. The issue is the compose-level dev configurations wrapping them.

## Solution

Pre-build Docker images in GitHub Actions CI, push to ghcr.io, and deploy by pulling images on the VPS. Only changed services are rebuilt.

### Architecture

```
git push main
  -> GitHub Actions: path-filter detects changed services
  -> Build ONLY changed images -> push to ghcr.io (3-5 min)
  -> Deploy job (gated on ALL builds passing) -> SSH to VPS
  -> docker compose pull + up -d (10 sec)
  -> Health check verification
```

## Deliverables

### 1. `docker-compose-deploy.yml` (New File)

A production-ready compose file that references pre-built images instead of building from source.

**Key properties:**
- All app services use `image: ghcr.io/mohamed-elkholy95/pythinker-<service>:<tag>`
- `IMAGE_TAG` env var controls the tag (default: `latest`)
- No `build:` directives on app services
- No `develop.watch` blocks
- Production entry points: `run.sh` for backend, Nginx for frontend
- Gateway shares the backend image with a different command (net-new in deploy — see note below)
- Infrastructure services (MongoDB, Redis, Qdrant, MinIO) remain unchanged (upstream images)
- Same `.env` file, same volumes
- Same healthchecks and resource limits as current dev compose

**Network topology:** Single flat `pythinker-network` bridge — matching the current dev compose behavior on the VPS. The production compose (`docker-compose-production.yml`) uses a two-network isolation model (`pythinker-prod` + `pythinker-backend-internal`), but adopting that topology is a separate concern and out of scope for this change. Database ports are already bound to `127.0.0.1` only, providing host-level isolation.

**Gateway note:** The gateway service exists in the dev compose but **not** in `docker-compose-production.yml`. Including it in `docker-compose-deploy.yml` is intentional — it matches the current running state on the VPS (the gateway container is running today). This is a deliberate choice to preserve current functionality, not an accidental addition.

**Services:**
| Service | Image Source | Entry Point |
|---------|-------------|-------------|
| frontend | `ghcr.io/.../pythinker-frontend:${IMAGE_TAG}` | Nginx (port 80 inside container, mapped to host 5174) |
| backend | `ghcr.io/.../pythinker-backend:${IMAGE_TAG}` | `run.sh` (uvicorn production) |
| gateway | `ghcr.io/.../pythinker-backend:${IMAGE_TAG}` | `python -m app.interfaces.gateway.gateway_runner` |
| sandbox | `ghcr.io/.../pythinker-sandbox:${IMAGE_TAG}` | Default (supervisord) |
| mongodb | `mongo:7.0.28` | Unchanged |
| redis | `redis:8.4-alpine` | Unchanged |
| qdrant | `qdrant/qdrant:v1.16.3` | Unchanged |
| minio | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | Unchanged |

**Port 5174 note:** The frontend is mapped to host port 5174 to match the current VPS setup. Dokploy/Traefik routes external traffic to this port. The container internally runs Nginx on port 80.

### 2. Modified CI Workflow (`.github/workflows/deploy.yml`)

**Changes from current:**
- **Trigger:** Add `push: branches: [main]` alongside existing `push: tags: [v*]`
- **Path filtering:** Use `dorny/paths-filter` to detect which services changed
- **Conditional builds:** Only build images for services with file changes. If no app files changed (e.g., docs-only commit), skip all builds and deploy.
- **Tagging strategy:**
  - On `main` push: `latest` + `sha-<short-hash>`
  - On version tag: semver tags (existing behavior preserved)
- **Deploy job:** Separate job with `needs: [build]` — only runs if **all** build matrix legs pass. This prevents version skew (e.g., new backend + old frontend).
- **Sandbox build arg:** `ENABLE_SANDBOX_ADDONS` defaults to `0` in CI. Can be overridden via `workflow_dispatch` input for custom builds.

**Path filter mapping:**
| Service | Paths |
|---------|-------|
| backend | `backend/**` |
| frontend | `frontend/**` |
| sandbox | `sandbox/**` |
| deploy_config | `docker-compose-deploy.yml` |

**Deploy-config-only pushes:** When only `docker-compose-deploy.yml` changes (no app code), the `any_app` flag is still `true` so the deploy job runs `git pull` + `docker compose up -d` to apply the updated compose config. No image builds are triggered.

Gateway does not need its own build — it uses the backend image.

### 3. Deploy Mechanism

**Method:** SSH from GitHub Actions to VPS after images are pushed.

**GitHub Secrets required:**
| Secret | Purpose |
|--------|---------|
| `VPS_SSH_KEY` | Private SSH key for VPS access |
| `VPS_HOST` | VPS hostname or IP |
| `VPS_USER` | SSH user (default: `root`) |

**Deploy directory:** `/opt/pythinker-deploy/` — a dedicated directory **outside** Dokploy's managed path (`/etc/dokploy/compose/...`). This avoids conflicts with Dokploy's internal git state. The deploy directory contains only:
- `docker-compose-deploy.yml` (pulled from repo via `git clone`/`git pull`)
- `.env` symlinked or copied from the Dokploy-managed `.env`

**Deploy commands (executed via SSH):**
```bash
# First-time setup (manual, one-time):
#   mkdir -p /opt/pythinker-deploy
#   cd /opt/pythinker-deploy
#   git clone https://github.com/mohamed-elkholy95/Pythinker.git .
#   cp /etc/dokploy/compose/pythinker-pythinker-akwnya/code/.env .env
#   docker compose -f docker-compose-deploy.yml pull
#   docker compose -f docker-compose-deploy.yml up -d

# CI deploy (every push):
cd /opt/pythinker-deploy
git pull origin main
docker compose -f docker-compose-deploy.yml pull
docker compose -f docker-compose-deploy.yml up -d --remove-orphans

# Health check (fail CI if unhealthy)
sleep 10
curl -fsS http://localhost:8000/api/v1/health || exit 1

# Cleanup
docker image prune -f
```

**Why separate directory:** Dokploy manages `/etc/dokploy/compose/pythinker-pythinker-akwnya/code/` and may pull/reset it during dashboard actions. Using `/opt/pythinker-deploy/` ensures CI and Dokploy never conflict.

### 4. Dokploy Configuration Change

- **Disable** Dokploy's auto-deploy-on-push for the Pythinker project
- Dokploy continues to provide: container monitoring, logs, dashboard visibility
- Deploy is now handled exclusively by CI
- The old containers under Dokploy's compose project will be stopped and replaced by containers from the new deploy directory

### 5. Rollback Strategy

To rollback to a previous version:
```bash
# On VPS
cd /opt/pythinker-deploy
IMAGE_TAG=sha-abc1234 docker compose -f docker-compose-deploy.yml pull
IMAGE_TAG=sha-abc1234 docker compose -f docker-compose-deploy.yml up -d
```

Every image is tagged with its commit SHA, so any previous build is pullable.

### 6. First-Time Setup Prerequisites

Before the first CI deploy can succeed:

1. **Seed the `latest` tag:** Run the CI workflow manually via `workflow_dispatch` (or push any change to `main`). This creates the initial `latest` tag on ghcr.io. Without this, `docker compose pull` will fail with "image not found."
2. **Create deploy directory on VPS:** Clone repo to `/opt/pythinker-deploy/`, copy `.env`.
3. **Add GitHub Secrets:** `VPS_SSH_KEY`, `VPS_HOST`, `VPS_USER`.
4. **Disable Dokploy auto-deploy** for the Pythinker project.
5. **Stop old Dokploy-managed containers:** Find Dokploy's compose dir (the path contains an installation-specific ID, e.g., `pythinker-pythinker-akwnya`). Verify the path on VPS with: `docker inspect <any-pythinker-container> --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'`. Then: `docker compose -f <path>/docker-compose.yml down` (data volumes persist).

### 7. Failure Handling

| Failure | Behavior |
|---------|----------|
| CI build fails (1 or more images) | Deploy job does **not** run. VPS stays on previous version. |
| VPS unreachable via SSH | Deploy job fails. Images are pushed to ghcr.io. Manual deploy possible. |
| Health check fails after deploy | CI reports failure. Operator can rollback via SHA tag. |
| `git pull` conflicts on VPS | Deploy fails. Manual resolution needed (should be rare — deploy dir only tracks compose files). |

## Security Improvements (Side Effects)

- No `--reload` flags in production (removes file watcher overhead)
- Nginx serves frontend with proper caching headers and gzip
- No `develop.watch` blocks (removes Docker API surface)
- Production-tuned uvicorn (worker recycling, graceful shutdown)

## What Does NOT Change

- `.env` file on VPS — same variables, same secrets
- Docker volumes — data persists across deploys
- Infrastructure services — MongoDB, Redis, Qdrant, MinIO untouched
- Dokploy dashboard — still shows all containers and logs
- Existing version-tag CI workflow — still works for releases

## Lessons Learned (2026-03-18 Incident)

During the first deployment attempt, four cascading issues were discovered:

### 1. Sandbox Supervisor Password Mismatch (FIXED — `sandbox/app/core/config.py`)

**Root cause:** The Pydantic `@model_validator` in sandbox config replaced `"supervisor-dev-password"` with a random token at runtime. But supervisord (the parent process) had already read the original env var value via `%(ENV_SUPERVISOR_RPC_PASSWORD)s` interpolation at startup. Result: 401 Unauthorized on every RPC call, sandbox app crashed to FATAL state.

**Fix:** The validator now has three branches:
1. `os.environ["SUPERVISOR_RPC_PASSWORD"]` is set (even to a default) → use it as-is
2. Env var is empty AND pydantic field is empty → generate random password + export to `os.environ`
3. Password set via `.env` file but not in `os.environ` → sync it to `os.environ`

All three paths ensure `os.environ` and `self.SUPERVISOR_RPC_PASSWORD` stay in sync with supervisord.

### 2. Container Name Conflict (FIXED — `docker-compose-deploy.yml`)

**Root cause:** `container_name: pythinker-qdrant` was hardcoded. If any other Compose project already had a container with that name (e.g., Dokploy's stack), `docker compose up` failed with "name already in use".

**Fix:** Removed all `container_name:` directives. Services are discoverable via Docker DNS using the Compose service name (e.g., `qdrant`), not the container name.

### 3. Volume & Network `external: true` Removal (FIXED — `docker-compose-deploy.yml`)

**Root cause:** Volumes and the network marked `external: true` required manual pre-creation before first deploy. If they didn't exist, `docker compose up` failed immediately.

**Fix:** Removed `external: true` from all five volume definitions and the `pythinker-network` network. Named volumes (with explicit `name:`) persist across `down`/`up` cycles by default and are auto-created on first run. The network is also auto-created with its explicit name.

### 4. Deploy Health Check Gap (FIXED — `.github/workflows/deploy.yml`)

**Root cause:** The deploy health check only verified the backend (`localhost:8000/health`). The sandbox could be down without CI noticing.

**Fix:** Added sandbox health check (`localhost:8083/health`) to the deploy verification step with the same 30-retry/2s-interval pattern.

## Non-Goals

- Multi-node / swarm deployment (single VPS)
- Blue-green or canary deployments (overkill for current scale)
- Helm/Kubernetes migration
- Two-network isolation topology (future enhancement, separate spec)
- Changing the production compose file (`docker-compose-production.yml` with Traefik) — that's a separate concern
