# Quick Start: Multi-Task System

## Prerequisites

- Docker and Docker Compose
- `.env` configured in repo root

## Start Stack

```bash
docker compose -f docker-compose.yml -f docker-compose-development.yml up -d --build
```

This starts:
- Frontend: `http://localhost:5174`
- Backend API: `http://localhost:8000`
- MongoDB, Redis, Qdrant
- Sandbox containers

## Validate Services

```bash
docker compose ps
curl -s http://localhost:8000/health
```

## Run a Multi-Task Session

1. Open `http://localhost:5174`.
2. Create a new agent session.
3. Submit a multi-step request (research + summarize + file output).
4. Observe:
   - Task progress in tool panel
   - Live computer view (CDP primary, VNC fallback)
   - Session replay availability in history

## Optional Backend Checks

```bash
conda activate pythinker
cd backend
ruff check .
ruff format --check .
pytest tests/
```
