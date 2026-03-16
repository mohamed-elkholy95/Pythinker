#!/bin/bash
# =============================================================================
# dev.sh — Pythinker development workflow
#
# Uses Docker Compose Watch for file sync + HMR. Compose Watch syncs files
# from the host into running containers via the Docker API (tar+cp), bypassing
# OrbStack's TCC/FDA bind-mount restriction on ~/Desktop/Projects. Files land
# on the container's native ext4 filesystem, giving instant inotify events to
# Vite and optional uvicorn --reload — no polling required.
#
# HMR flow:
#   Edit file → Compose Watch (tar+cp to container) → inotify fires →
#     Frontend: Vite HMR → instant browser update (no page reload)
#     Backend:  uvicorn --reload (default on) → Python auto-restart (~1s)
#     Sandbox:  uvicorn --reload → Python auto-restart (~1s)
#     Gateway:  sync+restart on code change (channel pipeline, Telegram etc.)
#
# Commands:
#   ./dev.sh                    Build + start full stack + live watch (DEFAULT)
#   ./dev.sh watch              Same as above (explicit)
#   ./dev.sh attach             Attach watch to ALREADY-RUNNING containers (no rebuild)
#   ./dev.sh up -d              Start without watch (no HMR — manual use only)
#   ./dev.sh logs -f backend    Follow backend logs
#   ./dev.sh down -v            Stop + remove volumes
#   ./dev.sh [--monitoring] <cmd>  Include Prometheus/Grafana stack
#
# Legacy (rsync fallback — only needed if compose watch doesn't work):
#   ./dev.sh sync               One-shot rsync backend + frontend to /private/tmp
#   ./dev.sh sync backend       Sync backend only
#   ./dev.sh sync frontend      Sync frontend only
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Legacy rsync helpers (fallback if compose watch isn't available) ──────────
# These sync source code to /private/tmp staging dirs for bind-mount fallback.
# With compose watch, these are only needed for one-off debugging.

BACKEND_SRC="$PROJECT_DIR/backend"
FRONTEND_SRC="$PROJECT_DIR/frontend"
BACKEND_TMP="/private/tmp/pythinker-backend"
FRONTEND_TMP="/private/tmp/pythinker-frontend"

sync_backend() {
    mkdir -p "$BACKEND_TMP"
    rsync -a --delete \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.venv/' \
        --exclude='.git/' \
        --exclude='*.egg-info/' \
        --exclude='.pytest_cache/' \
        "$BACKEND_SRC/" "$BACKEND_TMP/"
    echo "✓ Backend synced  →  $BACKEND_TMP"
}

sync_frontend() {
    mkdir -p "$FRONTEND_TMP"
    rsync -a --delete "$FRONTEND_SRC/src/"    "$FRONTEND_TMP/src/"
    rsync -a --delete "$FRONTEND_SRC/public/" "$FRONTEND_TMP/public/"
    for f in index.html package.json package-lock.json bun.lock \
              vite.config.ts tsconfig.json tsconfig.app.json \
              tsconfig.node.json env.d.ts; do
        [[ -f "$FRONTEND_SRC/$f" ]] && cp -f "$FRONTEND_SRC/$f" "$FRONTEND_TMP/$f"
    done
    echo "✓ Frontend synced →  $FRONTEND_TMP"
}

cmd_sync() {
    local target="${1:-all}"
    case "$target" in
        backend)  sync_backend ;;
        frontend) sync_frontend ;;
        all)      sync_backend; sync_frontend ;;
        *)
            echo "Usage: ./dev.sh sync [backend|frontend|all]" >&2
            exit 1
            ;;
    esac
}

# ── Docker Compose helpers ────────────────────────────────────────────────────

# Always run from project root so compose watch paths resolve correctly.
# This allows calling ./dev.sh from any working directory (e.g., from an IDE terminal).
cd "$PROJECT_DIR"

if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo "Error: Neither docker compose nor docker-compose found" >&2
    exit 1
fi

# Optional flags:
#   --monitoring -> include Prometheus + Grafana + Loki stack
COMPOSE_FILES="-f docker-compose-development.yml"
ENABLE_MONITORING=0
POSITIONAL_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --monitoring)
            ENABLE_MONITORING=1
            ;;
        *)
            POSITIONAL_ARGS+=("$arg")
            ;;
    esac
done
set -- "${POSITIONAL_ARGS[@]}"

if [[ "$ENABLE_MONITORING" -eq 1 ]]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose-monitoring.yml"
fi

# ── Dispatch ─────────────────────────────────────────────────────────────────

CMD="${1:-watch}"

case "$CMD" in
    watch)
        # Default dev workflow: build + start full stack + live file sync via Docker Compose Watch
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Pythinker Dev — Docker Compose Watch"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Frontend : ./frontend/src → /app/src  [Vite HMR]"
        echo "  Backend  : ./backend/app  → /app/app  [uvicorn --reload]"
        echo "  Sandbox  : ./sandbox/app  → /app/app  [uvicorn --reload]"
        echo "  Gateway  : ./backend/app  → /app/app  [sync+restart]"
        echo ""
        echo "  Tip: containers already running? Use ./dev.sh attach instead."
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        $COMPOSE $COMPOSE_FILES up --build --watch
        ;;
    attach)
        # Attach Compose Watch to ALREADY-RUNNING containers (no rebuild, no restart)
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Pythinker Dev — Attaching Compose Watch"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Watching for file changes (containers already running)..."
        echo "  Frontend : ./frontend/src → /app/src  [Vite HMR]"
        echo "  Backend  : ./backend/app  → /app/app  [uvicorn --reload]"
        echo "  Sandbox  : ./sandbox/app  → /app/app  [uvicorn --reload]"
        echo "  Gateway  : ./backend/app  → /app/app  [sync+restart]"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        $COMPOSE $COMPOSE_FILES watch --no-up --prune
        ;;
    sync)
        # Legacy: rsync to /private/tmp staging dirs
        shift
        cmd_sync "${1:-all}"
        ;;
    up|start|restart)
        # Pass through to docker compose (no auto-sync needed — image has source code)
        $COMPOSE $COMPOSE_FILES "$@"
        ;;
    *)
        # All other compose commands pass through unchanged
        $COMPOSE $COMPOSE_FILES "$@"
        ;;
esac
