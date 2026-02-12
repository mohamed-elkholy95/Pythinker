#!/bin/bash
set -e

# Start backend service
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
