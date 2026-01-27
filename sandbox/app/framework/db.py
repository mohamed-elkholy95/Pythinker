from typing import AsyncGenerator
import asyncio
import logging
import subprocess
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# Lazy engine - created on first use
_engine = None
_session_factory = None
_db_initialized = False


def _get_engine():
    """Get or create the database engine lazily."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.FRAMEWORK_DATABASE_URL,
            echo=settings.FRAMEWORK_DB_ECHO,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory():
    """Get or create the session factory lazily."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


async def _start_postgres() -> bool:
    """Start PostgreSQL via supervisorctl if not already running."""
    try:
        # Check if postgres is already running
        result = subprocess.run(
            ["supervisorctl", "-c", "/app/supervisord.conf", "status", "postgres"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "RUNNING" in result.stdout:
            logger.debug("PostgreSQL already running")
            return True

        # Start postgres
        logger.info("Starting PostgreSQL on-demand...")
        result = subprocess.run(
            ["supervisorctl", "-c", "/app/supervisord.conf", "start", "postgres"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.error(f"Failed to start PostgreSQL: {result.stderr}")
            return False

        # Wait for postgres to be ready
        for _ in range(30):
            await asyncio.sleep(0.5)
            result = subprocess.run(
                ["pg_isready", "-h", "127.0.0.1", "-p", "5432"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("PostgreSQL is ready")
                return True

        logger.error("PostgreSQL did not become ready in time")
        return False

    except Exception as e:
        logger.error(f"Error starting PostgreSQL: {e}")
        return False


async def ensure_db_ready() -> bool:
    """Ensure database is initialized. Starts PostgreSQL if needed."""
    global _db_initialized

    if _db_initialized:
        return True

    # Start PostgreSQL if not running
    if not await _start_postgres():
        return False

    # Initialize database schema
    max_retries = 10
    retry_delay = 0.5

    for attempt in range(1, max_retries + 1):
        try:
            async with _get_engine().begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _db_initialized = True
            logger.info("Framework database initialized successfully")
            return True
        except Exception as exc:
            if attempt == max_retries:
                logger.error(f"Failed to initialize database after {max_retries} attempts: {exc}")
                return False
            logger.warning(
                "Framework DB init failed (attempt %s/%s): %s",
                attempt,
                max_retries,
                exc,
            )
            await asyncio.sleep(retry_delay)

    return False


async def init_db() -> None:
    """Initialize database - now a no-op, initialization is lazy."""
    logger.info("Framework database will be initialized on first use (lazy loading)")


async def shutdown_db() -> None:
    """Shutdown database connection."""
    global _engine, _session_factory, _db_initialized
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        _db_initialized = False


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session. Ensures DB is ready before yielding."""
    if not await ensure_db_ready():
        raise RuntimeError("Database is not available")

    async with _get_session_factory()() as session:
        yield session
