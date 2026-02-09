# Container Log Monitoring Guide

## Quick Reference

### Using the Monitoring Script

```bash
# Make executable (first time)
chmod +x monitor_containers.sh

# Monitor all containers (default)
./monitor_containers.sh all
./monitor_containers.sh          # Same as 'all'

# Monitor specific services
./monitor_containers.sh sandbox
./monitor_containers.sh backend
./monitor_containers.sh frontend

# Monitor core services only
./monitor_containers.sh core     # Sandbox + Backend

# Monitor infrastructure
./monitor_containers.sh infra    # MongoDB, Redis, Qdrant

# Monitor search services
./monitor_containers.sh search   # Whoogle, SearXNG

# Show container statistics
./monitor_containers.sh stats

# Monitor errors only
./monitor_containers.sh errors

# Monitor context generation
./monitor_containers.sh context

# View/tail specific container
./monitor_containers.sh logs sandbox
./monitor_containers.sh tail backend
```

---

## Current Log Status

### All Containers Running ✓

```
• pythinker-backend-1        (Up, healthy)
• pythinker-frontend-dev-1   (Up, Vite dev server)
• pythinker-mockserver-1     (Up)
• pythinker-mongodb-1        (Up)
• pythinker-qdrant          (Up, healthy)
• pythinker-redis-1          (Up)
• pythinker-sandbox-1        (Up, healthy, context generated)
• pythinker-searxng-1        (Up)
• pythinker-whoogle-1        (Up, healthy)
```

### Key Observations

**✅ Sandbox (pythinker-sandbox-1):**
- Health checks passing every 10 seconds
- Context generation completed successfully
- VNC server running
- Chrome browser running
- All services operational

**✅ Backend (pythinker-backend-1):**
- API responding to requests
- Session management active
- Frontend polling every 10 seconds

**✅ Qdrant:**
- Vector database healthy
- Collection 'agent_memories' loaded
- REST API listening on port 6333

**✅ SearXNG:**
- Search engine running
- Worker spawned successfully
- Minor warnings for inactive engines (ahmia, torch) - normal

**✅ Whoogle:**
- Tor proxy running
- DDG bangs loaded
- Server running on port 5000

---

## Direct Docker Commands

### View Live Logs

```bash
# All containers
docker-compose -f docker-compose-development.yml logs -f

# Specific containers
docker logs -f pythinker-sandbox-1
docker logs -f pythinker-backend-1
docker logs -f pythinker-frontend-dev-1

# Multiple containers
docker-compose -f docker-compose-development.yml logs -f sandbox backend

# Last N lines then follow
docker logs -f --tail=100 pythinker-sandbox-1

# With timestamps
docker logs -f -t pythinker-backend-1

# Since specific time
docker logs --since 10m pythinker-sandbox-1
docker logs --since 2026-01-27T23:00:00 pythinker-backend-1
```

### Search Logs

```bash
# Search for errors
docker logs pythinker-backend-1 2>&1 | grep -i error

# Search for context generation
docker logs pythinker-sandbox-1 2>&1 | grep -i context

# Search for specific pattern
docker logs pythinker-backend-1 2>&1 | grep "shell_exec"

# Count occurrences
docker logs pythinker-backend-1 2>&1 | grep -c "error"
```

### Container Statistics

```bash
# Live stats (updates every second)
docker stats

# One-time snapshot
docker stats --no-stream

# Specific containers
docker stats pythinker-sandbox-1 pythinker-backend-1

# Custom format
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
```

### Container Inspection

```bash
# Container details
docker inspect pythinker-sandbox-1

# Specific field
docker inspect pythinker-sandbox-1 --format '{{.State.Status}}'

# All Pythinker containers
docker ps --filter "name=pythinker"

# Container health
docker inspect pythinker-sandbox-1 --format '{{.State.Health.Status}}'

# Environment variables
docker inspect pythinker-sandbox-1 --format '{{range .Config.Env}}{{println .}}{{end}}'
```

---

## Monitoring Patterns

### Context System Monitoring

**Monitor context generation at startup:**
```bash
docker logs -f pythinker-sandbox-1 | grep -E "(context|scan|generate)"
```

**Verify context files:**
```bash
docker exec pythinker-sandbox-1 ls -lh /app/sandbox_context.*
docker exec pythinker-sandbox-1 head -20 /app/sandbox_context.md
```

**Check context stats:**
```bash
docker exec pythinker-backend-1 python3 << 'EOF'
from app.domain.services.prompts.sandbox_context import SandboxContextManager
stats = SandboxContextManager.get_context_stats()
print(f"Available: {stats['available']}")
print(f"Version: {stats.get('version')}")
print(f"Age: {stats.get('age_hours')} hours")
EOF
```

### Agent Behavior Monitoring

**Monitor for exploratory commands (should be ZERO):**
```bash
docker logs -f pythinker-backend-1 | grep -E "(python3 --version|pip list|which git|node --version)"
```

**Monitor tool executions:**
```bash
docker logs -f pythinker-backend-1 | grep -E "shell_exec|file_write|file_read"
```

**Monitor agent sessions:**
```bash
docker logs -f pythinker-backend-1 | grep -E "session|agent|workflow"
```

### Performance Monitoring

**Watch resource usage:**
```bash
watch -n 1 'docker stats --no-stream'
```

**Monitor network traffic:**
```bash
docker stats --no-stream --format "table {{.Name}}\t{{.NetIO}}\t{{.BlockIO}}"
```

**Check disk usage:**
```bash
docker system df
docker system df -v
```

### Error Monitoring

**All errors from all containers:**
```bash
docker-compose -f docker-compose-development.yml logs --tail=1000 | \
  grep -iE "(error|exception|critical|fatal|traceback)"
```

**Backend errors only:**
```bash
docker logs pythinker-backend-1 2>&1 | \
  grep -iE "(error|exception|traceback)" | tail -50
```

**Sandbox errors only:**
```bash
docker logs pythinker-sandbox-1 2>&1 | \
  grep -iE "(error|failed|exception)" | tail -50
```

---

## Useful Shortcuts

### Dev Script Commands

```bash
# Start services
./dev.sh up -d

# Stop services
./dev.sh down

# Restart specific service
./dev.sh restart sandbox
./dev.sh restart backend

# View logs
./dev.sh logs -f sandbox
./dev.sh logs -f backend frontend

# Execute command in container
./dev.sh exec sandbox sh
./dev.sh exec backend python3 -c "print('hello')"

# Show service status
./dev.sh ps
```

### Quick Health Checks

```bash
# Check all container status
docker ps --filter "name=pythinker" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Health check endpoints
curl http://localhost:8000/health        # Backend
curl http://localhost:8080/health        # Sandbox
curl http://localhost:5174               # Frontend

# Service versions
docker exec pythinker-sandbox-1 python3 --version
docker exec pythinker-sandbox-1 node --version
```

---

## Log File Locations (Inside Containers)

### Sandbox Container

```
/var/log/supervisor/supervisord.log          # Supervisor main log
/var/log/supervisor/context_generator-*.log  # Context generation
/var/log/supervisor/app-*.log                # Sandbox API
/var/log/supervisor/chrome-*.log             # Chromium browser
/var/log/supervisor/x11vnc-*.log             # VNC server
```

### Backend Container

```
Application logs go to stdout/stderr (Docker logs)
```

### Access Logs Inside Containers

```bash
# Supervisor logs in sandbox
docker exec pythinker-sandbox-1 supervisorctl tail -f context_generator
docker exec pythinker-sandbox-1 supervisorctl tail app

# System logs
docker exec pythinker-sandbox-1 cat /var/log/supervisor/supervisord.log
```

---

## Troubleshooting Commands

### Container Won't Start

```bash
# Check exit code
docker inspect pythinker-sandbox-1 --format '{{.State.ExitCode}}'

# View full logs
docker logs pythinker-sandbox-1

# Check recent errors
docker logs pythinker-sandbox-1 2>&1 | tail -100
```

### High CPU/Memory Usage

```bash
# Identify culprit
docker stats --no-stream | sort -k3 -h

# Process list inside container
docker exec pythinker-sandbox-1 ps aux

# Top processes
docker exec pythinker-sandbox-1 top -b -n 1
```

### Network Issues

```bash
# Check container networking
docker network inspect pythinker-network

# Test connectivity
docker exec pythinker-backend-1 ping -c 3 pythinker-sandbox-1
docker exec pythinker-backend-1 curl http://pythinker-sandbox-1:8080/health

# Check port bindings
docker port pythinker-sandbox-1
```

---

## Advanced Monitoring

### Stream Logs to File

```bash
# Save all logs
docker-compose -f docker-compose-development.yml logs -f > logs/all_$(date +%Y%m%d_%H%M%S).log

# Save specific container
docker logs -f pythinker-sandbox-1 > logs/sandbox_$(date +%Y%m%d_%H%M%S).log &
```

### Real-time Log Analysis

```bash
# Count error frequency
docker logs -f pythinker-backend-1 | grep -i error | wc -l

# Extract timestamps
docker logs -t pythinker-backend-1 | tail -100

# Filter by time range
docker logs --since "2026-01-27T23:00:00" --until "2026-01-27T23:30:00" pythinker-backend-1
```

### Multi-Container Monitoring

```bash
# Multiple terminals with tmux
tmux new-session \; \
  split-window -h \; \
  split-window -v \; \
  select-pane -t 0 \; send-keys 'docker logs -f pythinker-sandbox-1' Enter \; \
  select-pane -t 1 \; send-keys 'docker logs -f pythinker-backend-1' Enter \; \
  select-pane -t 2 \; send-keys 'docker stats' Enter
```

---

## Log Rotation & Cleanup

### Check Log Sizes

```bash
# Docker log directory
sudo du -sh /var/lib/docker/containers/*/

# Specific container
docker inspect pythinker-sandbox-1 --format '{{.LogPath}}' | xargs du -sh
```

### Clean Up Old Logs

```bash
# Truncate logs (dangerous - backup first!)
truncate -s 0 $(docker inspect pythinker-sandbox-1 --format='{{.LogPath}}')

# Or use Docker log rotation (docker-compose.yml)
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

---

## Context-Specific Monitoring

### Monitor Context Generation Success

```bash
# Watch for context generation at startup
docker logs -f pythinker-sandbox-1 | grep -A5 -B5 "context_generator"

# Expected output:
# INFO spawned: 'context_generator' with pid 7
# Scanning sandbox environment...
# Environment scan complete!
# Context saved to /app/sandbox_context.json
# ✓ Sandbox context generation complete
# INFO exited: context_generator (exit status 0; expected)
```

### Monitor Agent Behavior (Context Usage)

```bash
# Should see ZERO of these:
docker logs -f pythinker-backend-1 | grep -E "python3 --version|which git|pip list"

# Should see these instead (direct actions):
docker logs -f pythinker-backend-1 | grep -E "file_write|shell_exec.*python3.*script"
```

---

## Summary

**Primary Monitoring Command:**
```bash
./monitor_containers.sh all
```

**Quick Health Check:**
```bash
./monitor_containers.sh stats
```

**Error Check:**
```bash
./monitor_containers.sh errors
```

**Context Check:**
```bash
./monitor_containers.sh context
```

All containers are currently running healthy with context system operational!
