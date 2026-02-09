# Quick Start

## Requirements

- Docker 20.10+
- Docker Compose
- Valid LLM API credentials in `.env`

## Recommended Startup (Development)

```bash
docker compose -f docker-compose.yml -f docker-compose-development.yml up -d --build
```

Access:
- Frontend: `http://localhost:5174`
- Backend API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

## Basic Verification

```bash
docker compose ps
curl -s http://localhost:8000/health
```

## Stop Stack

```bash
docker compose down
```

## Notes

- Live browser view is CDP-first with VNC fallback.
- Replay is OpenReplay-first with screenshot fallback.
- For full live/replay setup details, see `docs/guides/OPENREPLAY.md`.
