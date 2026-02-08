#!/bin/bash
# Pythinker Demo Mock Server
# Start with: ./dev.sh
# Frontend:   cd ../frontend && BACKEND_URL=http://localhost:8000 bun run dev

set -e

# Install deps if needed
if ! python -c "import fastapi, sse_starlette" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

exec uvicorn main:app --host 0.0.0.0 --port 8090 --reload
