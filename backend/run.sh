#!/bin/bash

# Workers default to $WEB_CONCURRENCY or 1.
# A single async worker handles thousands of concurrent I/O-bound requests
# (LLM calls, DB queries, SSE streams). Multiple workers only help for
# CPU-bound parallelism (rare in this backend). Scale up for multi-user.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${WEB_CONCURRENCY:-1}" \
  --timeout-graceful-shutdown 30 \
  --timeout-keep-alive "${UVICORN_KEEP_ALIVE:-30}" \
  --limit-max-requests "${UVICORN_MAX_REQUESTS:-10000}" \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --log-level "$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"