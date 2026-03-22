# Headless Environment — CLI-Only Access

You are running on a **headless Linux server** (MAC-2). There is NO desktop, NO GUI, NO browser window.

## What You CAN Do

- Run shell commands via bash
- Access APIs via `curl` or `http` (httpie)
- Control Docker containers via `docker compose` and `docker exec`
- Read/write/edit files on the filesystem
- Run tests, linters, and build tools
- View logs via `docker compose logs` or `docker logs`
- Interact with services via their HTTP APIs

## What You CANNOT Do

- Open a browser window or any GUI application
- Take screenshots of a desktop
- Use any graphical tool
- Access localhost URLs via a browser — use `curl`/`http` instead

## Service Endpoints (Development)

When the dev stack is running (`./dev.sh watch`), these services are available:

| Service   | URL                      | How to Test                                    |
|-----------|--------------------------|------------------------------------------------|
| Backend   | http://localhost:8000    | `curl http://localhost:8000/health`            |
| Frontend  | http://localhost:5174    | `curl -s http://localhost:5174 \| head -20`    |
| Sandbox   | http://localhost:8083    | `curl http://localhost:8083/health`            |
| MongoDB   | localhost:27017          | `docker exec pythinker-mongodb-1 mongosh --eval "db.stats()"` |
| Redis     | localhost:6379           | `docker exec pythinker-redis-1 redis-cli ping` |
| Qdrant    | http://localhost:6333    | `curl http://localhost:6333/healthz`           |

## Docker Commands

```bash
# Check container status
docker compose ps

# View logs (follow)
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f sandbox
docker compose logs --tail=50 backend

# Execute inside container
docker exec -it pythinker-backend-1 bash
docker exec pythinker-backend-1 python -c "import app; print('ok')"

# Start dev stack
./dev.sh watch

# Stop stack
docker compose down -v
```

## API Testing

```bash
# Backend health
curl http://localhost:8000/health

# Backend API (example)
curl -s http://localhost:8000/api/v1/sessions | python3 -m json.tool

# SSE stream (raw)
curl -N http://localhost:8000/api/v1/sessions/{session_id}/stream

# Create session
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'
```

## Important

- Always use `curl` or `http` to check if services are running before trying to interact with them
- If a service is unreachable, check `docker compose ps` and `docker compose logs <service>`
- The compose file is `docker-compose.yml` (no dev override file — dev.sh uses `--watch` flag)
