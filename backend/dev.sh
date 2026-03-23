#!/bin/bash

set -euo pipefail

reload_flag="${BACKEND_ENABLE_RELOAD:-1}"
timeout_graceful="${BACKEND_UVICORN_GRACEFUL_TIMEOUT:-120}"

uvicorn_args=(
  app.main:app
  --host 0.0.0.0
  --port "${BACKEND_PORT:-8000}"
)

case "${reload_flag,,}" in
  1|true|yes|on)
    uvicorn_args+=(
      --reload
      --reload-dir app
      --reload-exclude "tests/*"
      --reload-exclude "docs/*"
      --reload-exclude "*.md"
    )
    ;;
esac

uvicorn_args+=(
  --timeout-graceful-shutdown "${timeout_graceful}"
  --no-server-header
)

exec uvicorn "${uvicorn_args[@]}"
