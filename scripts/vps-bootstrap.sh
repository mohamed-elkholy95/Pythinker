#!/usr/bin/env bash
# =============================================================================
# Pythinker VPS Bootstrap — First-time setup for production deployment
#
# Usage:
#   scp scripts/vps-bootstrap.sh vps:/tmp/ && ssh vps "bash /tmp/vps-bootstrap.sh"
#
# Prerequisites:
#   - Docker and Docker Compose installed on VPS
#   - GH_TOKEN in .env with read:packages scope (for private GHCR images)
# =============================================================================
set -euo pipefail

DEPLOY_DIR="/opt/pythinker-deploy"
REPO_URL="https://github.com/mohamed-elkholy95/Pythinker.git"
COMPOSE_FILE="docker-compose-deploy.yml"

echo "=== Pythinker VPS Bootstrap ==="
echo ""

# 1. Clone or update repo
if [ -d "$DEPLOY_DIR/.git" ]; then
  echo "[1/6] Updating existing repo..."
  cd "$DEPLOY_DIR"
  git fetch origin main --quiet
  git reset --hard origin/main --quiet
else
  echo "[1/6] Cloning repo..."
  git clone --depth 1 --branch main "$REPO_URL" "$DEPLOY_DIR"
  cd "$DEPLOY_DIR"
fi

echo "[preflight] Validating compose configs..."
"$DEPLOY_DIR/scripts/validate_compose_configs.sh"

# 2. Check .env exists
if [ ! -f "$DEPLOY_DIR/.env" ]; then
  echo ""
  echo "[2/6] ERROR: .env file missing!"
  echo "  cp $DEPLOY_DIR/.env.example $DEPLOY_DIR/.env"
  echo "  Then edit .env with your configuration."
  exit 1
fi
echo "[2/6] .env file found"

# 3. GHCR authentication
echo "[3/6] Authenticating with GHCR..."
GHCR_TOKEN=$(grep '^GH_TOKEN=' "$DEPLOY_DIR/.env" | cut -d'=' -f2- || true)
if [ -z "${GHCR_TOKEN:-}" ]; then
  echo "  WARNING: GH_TOKEN not found in .env"
  echo "  GHCR pull may fail for private images."
  echo "  Add GH_TOKEN=ghp_xxx to .env (needs read:packages scope)"
else
  echo "$GHCR_TOKEN" | docker login ghcr.io -u mohamed-elkholy95 --password-stdin
fi

# 4. Create external network (Traefik routes via this network)
echo "[4/6] Ensuring dokploy-network exists..."
docker network create dokploy-network 2>/dev/null && echo "  Created dokploy-network" || echo "  dokploy-network already exists"

# 5. Pull images
echo "[5/6] Pulling images (this may take a few minutes)..."
docker compose -f "$COMPOSE_FILE" pull

# 6. Start stack
echo "[6/6] Starting stack..."
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo "=== Bootstrap complete ==="
echo ""
docker compose -f "$COMPOSE_FILE" ps --format 'table {{.Name}}\t{{.Status}}'
echo ""
echo "Next steps:"
echo "  1. Configure Traefik to route pythinker.com → frontend:80"
echo "  2. Verify: curl -s http://localhost:8000/api/v1/health"
