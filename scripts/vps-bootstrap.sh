#!/usr/bin/env bash
# =============================================================================
# Pythinker VPS Bootstrap — First-time setup for the watch-free compose stack
#
# Usage:
#   scp scripts/vps-bootstrap.sh vps:/tmp/ && ssh vps "bash /tmp/vps-bootstrap.sh"
#
# Prerequisites:
#   - Docker and Docker Compose installed on VPS
# =============================================================================
set -euo pipefail

DEPLOY_DIR="/opt/pythinker-deploy"
REPO_URL="https://github.com/mohamed-elkholy95/Pythinker.git"
COMPOSE_FILE="docker-compose-deploy.yml"

echo "=== Pythinker VPS Bootstrap ==="
echo ""

# 1. Clone or update repo
if [ -d "$DEPLOY_DIR/.git" ]; then
  echo "[1/4] Updating existing repo..."
  cd "$DEPLOY_DIR"
  git fetch origin main --quiet
  git reset --hard origin/main --quiet
else
  echo "[1/4] Cloning repo..."
  git clone --depth 1 --branch main "$REPO_URL" "$DEPLOY_DIR"
  cd "$DEPLOY_DIR"
fi

echo "[preflight] Validating compose configs..."
"$DEPLOY_DIR/scripts/validate_compose_configs.sh"

# 2. Check .env exists
if [ ! -f "$DEPLOY_DIR/.env" ]; then
  echo ""
  echo "[2/4] ERROR: .env file missing!"
  echo "  cp $DEPLOY_DIR/.env.example $DEPLOY_DIR/.env"
  echo "  Then edit .env with your configuration."
  exit 1
fi
echo "[2/4] .env file found"

# 3. Start stack
echo "[3/4] Starting stack..."
docker compose -f "$COMPOSE_FILE" up --build -d

echo ""
echo "=== Bootstrap complete ==="
echo ""
docker compose -f "$COMPOSE_FILE" ps --format 'table {{.Name}}\t{{.Status}}'
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:5174 for the frontend"
echo "  2. Verify: curl -s http://localhost:8000/api/v1/health"
