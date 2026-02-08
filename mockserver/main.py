"""Pythinker Demo Mock Server.

A complete standalone mock backend that serves all frontend API endpoints
using in-memory state. No external dependencies (MongoDB, Redis, Docker) needed.

Usage:
    cd mockserver
    pip install -r requirements.txt
    uvicorn main:app --port 8000 --reload
"""
from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Logging ──────────────────────────────────────────────────────────
logger = logging.getLogger("mockserver")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(handler)

# ── App ──────────────────────────────────────────────────────────────
app = FastAPI(title="Pythinker Demo Mock Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────────────
from routes.health import router as health_router
from routes.auth import router as auth_router
from routes.sessions import router as sessions_router
from routes.files import router as files_router
from routes.skills import router as skills_router
from routes.settings import router as settings_router
from routes.usage import router as usage_router
from routes.workspace import router as workspace_router
from routes.ratings import router as ratings_router
from routes.llm import router as llm_router

# All routes are prefixed with /api/v1 to match the real backend
PREFIX = "/api/v1"

app.include_router(health_router, prefix=PREFIX)
app.include_router(auth_router, prefix=PREFIX)
app.include_router(sessions_router, prefix=PREFIX)
app.include_router(files_router, prefix=PREFIX)
app.include_router(skills_router, prefix=PREFIX)
app.include_router(settings_router, prefix=PREFIX)
app.include_router(usage_router, prefix=PREFIX)
app.include_router(workspace_router, prefix=PREFIX)
app.include_router(ratings_router, prefix=PREFIX)

# LLM endpoint at /v1/chat/completions (no /api prefix — OpenAI-compatible)
app.include_router(llm_router)

# ── Seed Data ────────────────────────────────────────────────────────
@app.on_event("startup")
async def seed():
    from seed_data.users import seed_users
    from seed_data.sessions import seed_sessions

    seed_users()
    seed_sessions()
    logger.info("Mock server ready — seeded demo user + 3 sessions")
    logger.info("Auth bypass: GET /api/v1/auth/status → auth_provider='none'")
    logger.info("Frontend: cd frontend && BACKEND_URL=http://localhost:8000 bun run dev")


# ── Root ─────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name": "Pythinker Demo Mock Server",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": f"{PREFIX}/*",
    }
