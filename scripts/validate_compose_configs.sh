#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

compose_files=(
  "docker-compose-deploy.yml"
  "docker-compose-production.yml"
)

cd "$ROOT_DIR"

for compose_file in "${compose_files[@]}"; do
  echo "Validating ${compose_file}..."
  docker compose -f "${compose_file}" config --no-interpolate >/dev/null
done

echo "Compose validation passed."
