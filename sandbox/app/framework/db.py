from typing import AsyncGenerator
import logging

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


async def ensure_db_ready() -> bool:
    """Ensure database is initialized (SQLite - instant, no startup needed)."""
    global _db_initialized

    if _db_initialized:
        return True

    # Initialize database schema (SQLite auto-creates the file)
    try:
        async with _get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_initialized = True
        logger.info("Framework database (SQLite) initialized successfully")
        return True
    except Exception as exc:
        logger.error(f"Failed to initialize SQLite database: {exc}")
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
