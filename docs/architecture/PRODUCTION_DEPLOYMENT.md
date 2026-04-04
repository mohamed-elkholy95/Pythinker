# Deployment Guide

## Current Stack

`docker-compose-deploy.yml` is now the watch-free deployment entrypoint for both local and VPS-style runs. It matches the dev container layout and startup behavior, but does not use Compose Watch.

The stack runs as direct Docker services:

- `frontend`: Vite dev server on `5174`
- `backend`: FastAPI + `uvicorn --reload` on `8000`
- `gateway`: opt-in channel runner, same backend image
- `sandbox`: hardened local sandbox container
- `mongodb`: standalone auth-enabled MongoDB
- `redis`: local Redis without password auth
- `qdrant`: local vector store
- `minio` + `minio-init`: object storage and bucket bootstrap

There is no Traefik, no Dokploy routing, and no backend replica set in this compose file.

## Required Environment Variables

Create a `.env` file in the project root. The compose file already provides safe defaults for most development values, but the following are the important overrides if you want to customize the stack:

```bash
MONGODB_DATABASE=pythinker
MONGODB_USERNAME=pythinker_admin
MONGODB_PASSWORD=change-me-mongodb-password

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

SANDBOX_API_SECRET=dev-sandbox-secret
SANDBOX_LIFECYCLE_MODE=static
SANDBOX_ADDRESS=sandbox

BACKEND_ENABLE_RELOAD=1
BACKEND_UVICORN_GRACEFUL_TIMEOUT=120
```

## Start

```bash
docker compose -f docker-compose-deploy.yml up --build -d
```

If you need to reset the local data volumes and MongoDB health state, use:

```bash
docker compose -f docker-compose-deploy.yml down -v
```

## Verify

```bash
docker compose -f docker-compose-deploy.yml ps
docker compose -f docker-compose-deploy.yml logs -f mongodb
docker compose -f docker-compose-deploy.yml exec mongodb mongosh --eval "db.runCommand({ping:1})"
```

## Ports

- Frontend: `http://localhost:5174`
- Backend: `http://localhost:8000`
- MongoDB: `localhost:27017`
- MinIO API: `localhost:9010`
- MinIO Console: `localhost:9011`
- Qdrant REST: `localhost:6333`
- Qdrant gRPC: `localhost:6334`
- Sandbox CDP/VNC surfaces: `8082`, `8083`, `8443`

## Historical Notes

Older docs in this repo may still describe a Dokploy + Traefik + GHCR workflow. That was the previous deployment model and is no longer the current `docker-compose-deploy.yml` layout.
