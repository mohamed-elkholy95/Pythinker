from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.core.middleware import SandboxAuthMiddleware
from app.framework.db import init_db, shutdown_db
from app.framework.router import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    logger.info("Sandbox framework database initialized")
    try:
        yield
    finally:
        await shutdown_db()
        logger.info("Sandbox framework database connection closed")


app = FastAPI(
    title="Sandbox Agent Framework",
    version="0.1.0",
    lifespan=lifespan,
)

# Shared secret auth — same secret protects both sandbox API and framework API
app.add_middleware(SandboxAuthMiddleware)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "sandbox-framework"}
