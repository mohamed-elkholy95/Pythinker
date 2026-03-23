#!/usr/bin/env bash
# Capture container resource snapshot for before/after comparison
set -euo pipefail

echo "=== Container Resource Snapshot ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

echo "--- Docker Stats ---"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}"
echo ""

echo "--- Docker Images ---"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -i pythinker || true
echo ""

echo "--- Docker System DF ---"
docker system df
echo ""

echo "--- Sandbox Supervisor Status ---"
docker exec pythinker-sandbox-1 supervisorctl status 2>/dev/null || echo "(sandbox not running)"
echo ""

echo "=== Snapshot Complete ==="
