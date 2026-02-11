#!/bin/bash

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --reload-dir app \
  --reload-exclude "tests/*" \
  --reload-exclude "docs/*" \
  --reload-exclude "*.md" \
  --timeout-graceful-shutdown 3
