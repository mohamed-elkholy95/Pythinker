---
name: sandbox-management
description: Docker sandbox container lifecycle management — static/dynamic provisioning, health checks, networking, and security configuration
---

# Sandbox Management Skill

## When to Use
When working with sandbox containers, Docker Compose configuration, or container lifecycle code.

## Architecture

### Container Types
- **Static mode** (default): Pre-provisioned `sandbox` and `sandbox2` containers
- **Dynamic mode**: On-demand container creation via Docker API

### Port Mapping
| Service | API Port | Framework Port | CDP Port |
|---------|----------|----------------|----------|
| sandbox | 8083 | 8082 | 9222 |
| sandbox2 | 8084 | 8085 | — |

### Networks
- `pythinker-network`: Public-facing bridge (frontend, backend, sandbox)
- `pythinker-backend-internal`: Internal-only (MongoDB, Redis, Qdrant)

### Security
- `security_opt: [no-new-privileges]`
- Non-root user inside containers
- `SANDBOX_API_SECRET` for backend↔sandbox auth

### Health Checks
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8083/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

## Key Files
- `docker-compose.yml` — Production service definitions
- `docker-compose-development.yml` — Dev overrides with Compose Watch
- `sandbox/` — Container image (Dockerfile, scripts, runtime requirements)
- `backend/app/core/sandbox_manager.py` — Container lifecycle management
- `backend/app/infrastructure/browser/` — Browser adapter using sandbox CDP

## Docker Compose Watch
File edits sync into containers via Docker API (tar+cp), bypassing bind-mount restrictions. Inotify fires immediately for HMR.
