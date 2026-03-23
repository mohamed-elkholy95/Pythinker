#!/usr/bin/env bash
# Safe, filtered Docker cache cleanup for Pythinker development.
#
# Removes:
#   - Dangling images (untagged intermediate layers)
#   - Build cache entries older than 7 days
#   - Stopped containers older than 24 hours
#
# Does NOT remove:
#   - Named volumes (mongodb_data, redis_data, qdrant_data, etc.)
#   - Tagged images (pythinker-backend, pythinker-sandbox, etc.)
#   - Running containers
#
# Usage:
#   ./scripts/prune_docker_cache.sh            # Execute cleanup
#   ./scripts/prune_docker_cache.sh --dry-run  # Preview only
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[DRY RUN] Showing what would be cleaned (no changes made)"
    echo ""
fi

echo "=== Docker Cache Cleanup ==="
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# 1. Dangling images
echo "--- Dangling Images ---"
DANGLING=$(docker images -f "dangling=true" -q 2>/dev/null | wc -l | tr -d ' ')
echo "Found: ${DANGLING} dangling image(s)"
if [[ "$DRY_RUN" == "false" && "$DANGLING" -gt 0 ]]; then
    docker image prune -f
    echo "Cleaned."
fi
echo ""

# 2. Build cache older than 7 days
echo "--- Build Cache (older than 7 days) ---"
if [[ "$DRY_RUN" == "true" ]]; then
    docker buildx du 2>/dev/null | tail -1 || echo "(buildx not available)"
else
    docker buildx prune --filter "until=168h" -f 2>/dev/null || \
        docker builder prune --filter "until=168h" -f 2>/dev/null || \
        echo "(build cache prune not available)"
fi
echo ""

# 3. Stopped containers older than 24 hours
echo "--- Stopped Containers (older than 24h) ---"
if [[ "$DRY_RUN" == "true" ]]; then
    docker ps -a --filter "status=exited" --filter "until=24h" --format "{{.Names}}\t{{.Status}}" 2>/dev/null || true
else
    docker container prune --filter "until=24h" -f 2>/dev/null || true
fi
echo ""

# Summary
echo "--- Current State ---"
docker system df
echo ""
echo "=== Cleanup Complete ==="
echo ""
echo "NOT removed: named volumes, tagged images, running containers."
echo "To see volumes: docker volume ls"
