import logging
from functools import lru_cache

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.websockets import WebSocket

from app.application.errors.exceptions import UnauthorizedError

# Import all required services
from app.application.services.agent_service import AgentService
from app.application.services.auth_service import AuthService
from app.application.services.email_service import EmailService
from app.application.services.file_service import FileService
from app.application.services.rating_service import RatingService
from app.application.services.rating_service import get_rating_service as _get_rating_service
from app.application.services.screenshot_service import (
    ScreenshotQueryService,
)
from app.application.services.screenshot_service import (
    get_screenshot_query_service as _get_screenshot_query_service,
)
from app.application.services.settings_service import SettingsService
from app.application.services.settings_service import get_settings_service as _get_settings_service
from app.application.services.token_service import TokenService
from app.core.config import get_settings
from app.domain.models.user import User, UserRole
from app.domain.services.memory_service import MemoryService
from app.infrastructure.external.cache import get_cache

# Import all required dependencies for agent service
from app.infrastructure.external.llm import get_llm
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox
from app.infrastructure.external.search import get_search_engine
from app.infrastructure.external.task.redis_task import RedisStreamTask
from app.infrastructure.repositories.file_mcp_repository import FileMCPRepository
from app.infrastructure.repositories.mongo_agent_repository import MongoAgentRepository
from app.infrastructure.repositories.mongo_memory_repository import MongoMemoryRepository
from app.infrastructure.repositories.mongo_session_repository import MongoSessionRepository
from app.infrastructure.repositories.user_repository import MongoUserRepository
from app.infrastructure.storage.mongodb import get_mongodb
from app.infrastructure.utils.llm_json_parser import LLMJsonParser

# Configure logging
logger = logging.getLogger(__name__)

# Security scheme - Bearer Token only
security_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_file_storage():
    """Get file storage instance based on FILE_STORAGE_BACKEND configuration."""
    settings = get_settings()
    if settings.file_storage_backend == "minio":
        from app.infrastructure.external.file.minios3storage import MinIOFileStorage
        from app.infrastructure.storage.minio_storage import get_minio_storage

        return MinIOFileStorage(minio_storage=get_minio_storage())

    from app.infrastructure.external.file.gridfsfile import GridFSFileStorage
    from app.infrastructure.storage.mongodb import get_mongodb

    return GridFSFileStorage(mongodb=get_mongodb())


def _get_llm_instance():
    """Get LLM instance using factory pattern.

    Uses the LLM provider factory to dynamically select the appropriate
    LLM implementation based on LLM_PROVIDER configuration.

    Raises RuntimeError if factory fails to ensure proper configuration.
    """
    llm = get_llm()
    if llm is None:
        raise RuntimeError("Failed to initialize LLM from factory. Check LLM_PROVIDER configuration.")
    return llm


@lru_cache
def get_memory_service() -> MemoryService | None:
    """
    Get memory service instance for long-term memory retrieval.

    Phase 6: Qdrant integration - this service enables semantic memory
    search using Qdrant for fast vector similarity.

    Returns None if initialization fails (graceful degradation).
    """
    try:
        logger.info("Creating MemoryService instance")
        settings = get_settings()
        db = get_mongodb().client[settings.mongodb_database]
        memory_repository = MongoMemoryRepository(db)
        llm = _get_llm_instance()
        return MemoryService(repository=memory_repository, llm=llm)
    except Exception as e:
        logger.warning(f"Failed to create MemoryService (graceful degradation): {e}")
        return None


@lru_cache
def get_agent_service() -> AgentService:
    """
    Get agent service instance with all required dependencies

    This function creates and returns an AgentService instance with all
    necessary dependencies. Uses lru_cache for singleton pattern.
    """
    logger.info("Creating AgentService instance")

    # Create all dependencies using factory pattern
    llm = _get_llm_instance()
    agent_repository = MongoAgentRepository()
    session_repository = MongoSessionRepository()
    sandbox_cls = DockerSandbox
    task_cls = RedisStreamTask
    json_parser = LLMJsonParser()
    file_storage = get_file_storage()
    search_engine = get_search_engine()
    mcp_repository = FileMCPRepository()
    memory_service = get_memory_service()  # Phase 6: Qdrant integration

    # Get MongoDB database for LangGraph checkpointing
    settings = get_settings()
    mongodb_db = None
    if settings.feature_workflow_checkpointing:
        try:
            mongodb_db = get_mongodb().client[settings.mongodb_database]
            logger.info("MongoDB database configured for LangGraph checkpointing")
        except Exception as e:
            logger.warning(f"Failed to get MongoDB for checkpointing: {e}")

    # Create AgentService instance
    return AgentService(
        llm=llm,
        agent_repository=agent_repository,
        session_repository=session_repository,
        sandbox_cls=sandbox_cls,
        task_cls=task_cls,
        json_parser=json_parser,
        file_storage=file_storage,
        search_engine=search_engine,
        mcp_repository=mcp_repository,
        memory_service=memory_service,
        mongodb_db=mongodb_db,
    )


@lru_cache
def get_file_service() -> FileService:
    """
    Get file service instance with required dependencies

    This function creates and returns a FileService instance with
    the necessary file storage and token service dependencies.
    """
    logger.info("Creating FileService instance")

    # Get dependencies
    file_storage = get_file_storage()
    token_service = get_token_service()

    return FileService(
        file_storage=file_storage,
        token_service=token_service,
    )


@lru_cache
def get_auth_service() -> AuthService:
    """
    Get authentication service instance with required dependencies

    This function creates and returns an AuthService instance with
    the necessary user repository dependency.
    """
    logger.info("Creating AuthService instance")

    # Get user repository dependency
    user_repository = MongoUserRepository()

    return AuthService(
        user_repository=user_repository,
        token_service=get_token_service(),
    )


@lru_cache
def get_token_service() -> TokenService:
    """Get token service instance"""
    logger.info("Creating TokenService instance")
    return TokenService()


@lru_cache
def get_email_service() -> EmailService:
    """Get email service instance"""
    logger.info("Creating EmailService instance")
    cache = get_cache()
    return EmailService(cache=cache)


def get_sandbox_cls():
    """Get sandbox class for dependency injection"""
    return DockerSandbox


@lru_cache
def get_settings_service() -> SettingsService:
    """Get settings service instance."""
    return _get_settings_service()


@lru_cache
def get_rating_service() -> RatingService:
    """Get rating service instance."""
    return _get_rating_service()


@lru_cache
def get_screenshot_query_service() -> ScreenshotQueryService:
    """Get screenshot query service instance."""
    return _get_screenshot_query_service()


def get_session_repository() -> MongoSessionRepository:
    """Get session repository instance for dependency injection (Priority 6: rating security)."""
    return MongoSessionRepository()


def increment_rating_unauthorized_attempts() -> None:
    """Record unauthorized rating attempts via observability adapter."""
    from app.infrastructure.observability.prometheus_metrics import rating_unauthorized_attempts_total

    rating_unauthorized_attempts_total.inc({})


async def get_current_user(
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """
    Get current authenticated user (required)

    This dependency enforces authentication using Bearer Token.
    If authentication fails, it raises an UnauthorizedError.
    """
    settings = get_settings()

    # If auth_provider is 'none', return anonymous user
    if settings.auth_provider == "none":
        return User(
            id="anonymous", fullname="anonymous", email="anonymous@localhost", role=UserRole.USER, is_active=True
        )

    # Check if bearer token is provided
    if not bearer_credentials:
        raise UnauthorizedError("Authentication required")

    try:
        # Verify bearer token
        user = await auth_service.verify_token(bearer_credentials.credentials)

        if not user:
            raise UnauthorizedError("Invalid token")

        if not user.is_active:
            raise UnauthorizedError("User account is inactive")

        return user

    except Exception as e:
        logger.warning(f"Authentication failed: {e}")
        raise UnauthorizedError("Authentication failed") from e


async def get_eventsource_current_user(
    access_token: str | None = Query(default=None),
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """Authenticate EventSource requests.

    Native browser EventSource does not support custom Authorization headers.
    This dependency allows fallback auth via query token for SSE GET endpoints,
    while still preferring standard bearer auth when available.
    """
    settings = get_settings()

    if settings.auth_provider == "none":
        return User(
            id="anonymous", fullname="anonymous", email="anonymous@localhost", role=UserRole.USER, is_active=True
        )

    token = bearer_credentials.credentials if bearer_credentials else access_token
    if not token:
        raise UnauthorizedError("Authentication required")

    try:
        user = await auth_service.verify_token(token)
        if not user:
            raise UnauthorizedError("Invalid token")
        if not user.is_active:
            raise UnauthorizedError("User account is inactive")
        return user
    except Exception as e:
        logger.warning(f"EventSource authentication failed: {e}")
        raise UnauthorizedError("Authentication failed") from e


async def get_optional_current_user(
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    auth_service: AuthService = Depends(get_auth_service),
) -> User | None:
    """
    Get current authenticated user (optional)

    This dependency allows both authenticated and anonymous access.
    Returns None if authentication fails or is not provided.

    Uses Bearer Token authentication.
    """
    settings = get_settings()

    # If auth_provider is 'none', return anonymous user
    if settings.auth_provider == "none":
        return User(
            id="anonymous", fullname="anonymous", email="anonymous@localhost", role=UserRole.USER, is_active=True
        )

    # If no bearer token provided, return None
    if not bearer_credentials:
        return None

    try:
        # Try to verify bearer token
        user = await auth_service.verify_token(bearer_credentials.credentials)

        if user and user.is_active:
            return user

    except Exception as e:
        logger.warning(f"Optional authentication failed: {e}")

    return None


async def verify_signature(
    request: Request,
    signature: str | None = Query(None),
    token_service: TokenService = Depends(get_token_service),
) -> str:
    return await _verify_signature(request, signature, token_service)


async def verify_signature_websocket(
    request: WebSocket,
    signature: str | None = Query(None),
    token_service: TokenService = Depends(get_token_service),
) -> str:
    return await _verify_signature(request, signature, token_service)


async def _verify_signature(
    request: Request | WebSocket,
    signature: str | None = Query(None),
    token_service: TokenService = Depends(get_token_service),
) -> str:
    """
    Verify signature for signed URL access

    This dependency validates the signature parameter in the request URL.
    If the signature is missing or invalid, it raises an HTTPException.

    This is designed to work with both regular HTTP endpoints and WebSocket endpoints.
    For WebSocket connections, the exception will be raised before the connection is accepted,
    preventing invalid connections from being established.

    Args:
        request: The incoming request
        signature: The signature query parameter
        token_service: Token service for signature verification

    Returns:
        The verified signature string

    Raises:
        HTTPException: If signature is missing or invalid (status code 401)
    """
    if not signature:
        logger.error("Missing signature for path: %s", request.url.path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")

    if not token_service.verify_signed_url(str(request.url)):
        logger.error("Invalid signature for path: %s", request.url.path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    return signature


def extract_user_id_from_signed_url(
    request: Request = None,
    websocket: WebSocket = None,
) -> str | None:
    """Extract user_id from signed URL query parameter.

    This dependency extracts the 'uid' parameter from signed URLs,
    which binds the URL to a specific user for authorization.

    Args:
        request: HTTP request (for regular endpoints)
        websocket: WebSocket connection (for WebSocket endpoints)

    Returns:
        User ID from 'uid' parameter, or None if not present

    Context7 validated: Query parameter extraction pattern.
    """
    import urllib.parse

    # Get URL from either request or websocket
    if websocket:
        url_str = str(websocket.url)
    elif request:
        url_str = str(request.url)
    else:
        return None

    # Parse URL and extract uid parameter
    parsed_url = urllib.parse.urlparse(url_str)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    user_id = query_params.get("uid", [None])[0]

    return user_id
