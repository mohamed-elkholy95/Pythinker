#!/bin/bash

# Workers default to $WEB_CONCURRENCY (Uvicorn convention) or 4.
# Each worker runs its own async event loop — scale with CPU cores.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${WEB_CONCURRENCY:-4}" \
  --timeout-graceful-shutdown 30