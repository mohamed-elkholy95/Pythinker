import logging
from functools import lru_cache
from inspect import isawaitable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

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

if TYPE_CHECKING:
    from app.application.services.browser_workflow_service import BrowserWorkflowService

# Configure logging
logger = logging.getLogger(__name__)

# Security scheme - Bearer Token only
security_bearer = HTTPBearer(auto_error=False)


def _normalize_sandbox_base_url(raw_address: str | None) -> str | None:
    """Normalize SANDBOX_ADDRESS for Mermaid renderers.

    Supports the existing static-sandbox format where multiple addresses may be
    provided as a comma-separated list.
    """
    if not raw_address:
        return None

    address = next((part.strip() for part in raw_address.split(",") if part.strip()), "")
    if not address:
        return None

    candidate = address if "://" in address else f"http://{address}"
    parsed = urlsplit(candidate)
    if not parsed.hostname:
        return None

    scheme = parsed.scheme or "http"
    port = parsed.port or 8080
    return urlunsplit((scheme, f"{parsed.hostname}:{port}", "", "", ""))


def _build_mermaid_preprocessor(sandbox_url: str | None):
    """Build a MermaidPreprocessor with a sandbox HTTP client.

    Returns None when no sandbox URL is configured.
    This helper lives in the interfaces composition root so that the domain
    MermaidPreprocessor class stays free of infrastructure imports.
    """
    if not sandbox_url:
        return None

    import httpx

    from app.domain.services.pdf.mermaid_preprocessor import MermaidPreprocessor

    client = httpx.AsyncClient(base_url=sandbox_url, timeout=20.0)
    return MermaidPreprocessor(http_client=client, sandbox_url=sandbox_url)


def build_pdf_renderer_from_settings(settings: Any):
    """Return the configured report PDF renderer with safe fallback."""
    from app.domain.services.pdf.reportlab_pdf_renderer import ReportLabPdfRenderer

    # Determine sandbox URL for Mermaid diagram rendering
    sandbox_url = _normalize_sandbox_base_url(getattr(settings, "sandbox_address", None))
    mermaid = _build_mermaid_preprocessor(sandbox_url)

    reportlab_renderer = ReportLabPdfRenderer(mermaid=mermaid)
    renderer_choice = (getattr(settings, "telegram_pdf_renderer", "reportlab") or "reportlab").strip().lower()

    if renderer_choice == "playwright":
        try:
            from app.infrastructure.external.pdf import PlaywrightPdfRenderer

            timeout_ms = int(getattr(settings, "telegram_pdf_renderer_timeout_ms", 20_000))
            return PlaywrightPdfRenderer(
                timeout_ms=timeout_ms,
                fallback_renderer=reportlab_renderer,
                mermaid=mermaid,
            )
        except Exception as exc:
            logger.warning("Failed to initialize Playwright PDF renderer; using ReportLab fallback: %s", exc)

    return reportlab_renderer


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

        # Inject outbox repository for reliable sync (Phase 2)
        outbox_repo = None
        try:
            from app.infrastructure.repositories.sync_outbox_repository import SyncOutboxRepository

            outbox_repo = SyncOutboxRepository()
        except Exception as outbox_err:
            logger.warning(f"SyncOutboxRepository unavailable (sync disabled): {outbox_err}")

        return MemoryService(repository=memory_repository, llm=llm, outbox_repo=outbox_repo)
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


@lru_cache
def get_browser_workflow_service() -> "BrowserWorkflowService":
    """Get BrowserWorkflowService using the cached composition-root pattern."""
    from app.application.services.browser_workflow_service import BrowserWorkflowService
    from app.infrastructure.external.scraper.scrapling_adapter import get_scraping_adapter

    return BrowserWorkflowService(
        scraper=get_scraping_adapter(),
        settings=get_settings(),
    )


def get_session_repository() -> MongoSessionRepository:
    """Get session repository instance for dependency injection (Priority 6: rating security)."""
    return MongoSessionRepository()


@lru_cache
def get_prompt_profile_repository():
    """Get the shared MongoPromptProfileRepository singleton.

    The same instance satisfies both the PromptProfileRepository and
    OptimizationRunRepository protocols.
    """
    from app.infrastructure.repositories.mongo_prompt_profile_repository import (
        MongoPromptProfileRepository,
    )

    return MongoPromptProfileRepository()


@lru_cache
def get_prompt_artifact_repository():
    """Get the shared GridFSPromptArtifactRepository singleton."""
    from app.infrastructure.repositories.gridfs_prompt_artifact_repository import (
        GridFSPromptArtifactRepository,
    )

    return GridFSPromptArtifactRepository()


@lru_cache
def get_prompt_optimization_service():
    """Get the shared PromptOptimizationService singleton.

    Uses the same MongoPromptProfileRepository instance for both
    PromptProfileRepository and OptimizationRunRepository protocols.
    """
    from app.application.services.prompt_optimization_service import PromptOptimizationService

    repo = get_prompt_profile_repository()
    artifact = get_prompt_artifact_repository()
    return PromptOptimizationService(
        profile_repo=repo,
        run_repo=repo,
        artifact_repo=artifact,
    )


@lru_cache
def get_knowledge_base_service():
    """Get knowledge base service, or None if disabled / raganything not installed."""
    settings = get_settings()
    if not settings.knowledge_base_enabled:
        return None

    try:
        from app.domain.services.knowledge_base_service import KnowledgeBaseService
        from app.infrastructure.external.embedding.client import get_embedding_client
        from app.infrastructure.external.raganything.adapter import RAGAnythingAdapter
        from app.infrastructure.repositories.mongo_knowledge_repository import MongoKnowledgeRepository

        llm = _get_llm_instance()
        embedding_client = get_embedding_client()
        adapter = RAGAnythingAdapter(settings=settings, llm=llm, embedding_client=embedding_client)
        mongodb_db = get_mongodb().client[settings.mongodb_database]
        repository = MongoKnowledgeRepository(db=mongodb_db)
        return KnowledgeBaseService(repository=repository, adapter=adapter, settings=settings)
    except ImportError:
        logger.warning("raganything not installed; knowledge base feature disabled")
        return None
    except Exception as exc:
        logger.warning("Failed to create KnowledgeBaseService (graceful degradation): %s", exc)
        return None


def increment_rating_unauthorized_attempts() -> None:
    """Record unauthorized rating attempts via observability adapter."""
    from app.core.prometheus_metrics import rating_unauthorized_attempts_total

    rating_unauthorized_attempts_total.inc({})


def _raise_auth_error(reason: str | None) -> None:
    """Raise standardized UnauthorizedError with machine-readable code."""
    headers = {"WWW-Authenticate": "Bearer"}
    if reason == "token_expired":
        raise UnauthorizedError(
            "Access token has expired",
            error_code="token_expired",
            headers=headers,
        )
    if reason in {"invalid_token", "invalid_token_type", "token_verification_failed", "token_revoked", "user_inactive"}:
        raise UnauthorizedError(
            "Could not validate credentials",
            error_code="invalid_token",
            headers=headers,
        )
    raise UnauthorizedError(
        "Authentication required",
        error_code="auth_required",
        headers=headers,
    )


async def _verify_token_with_reason(auth_service: AuthService, token: str) -> tuple[User | None, str | None]:
    """Compatibility wrapper for auth_service token verification APIs."""
    modern = getattr(auth_service, "verify_token_secure_with_reason", None)
    if callable(modern):
        modern_result = modern(token)
        if isawaitable(modern_result):
            modern_result = await modern_result
        if (
            isinstance(modern_result, tuple)
            and len(modern_result) == 2
            and (modern_result[0] is None or isinstance(modern_result[0], User))
        ):
            user_value = modern_result[0]
            reason_value = modern_result[1]
            if reason_value is None or isinstance(reason_value, str):
                return user_value, reason_value

    legacy = getattr(auth_service, "verify_token_secure", None)
    if callable(legacy):
        legacy_result = legacy(token)
        if isawaitable(legacy_result):
            legacy_result = await legacy_result
        if legacy_result and isinstance(legacy_result, User):
            return legacy_result, None
        return None, "invalid_token"

    return None, "invalid_token"


async def require_admin_user(
    bearer_credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """Require authenticated user with admin role.

    This dependency enforces that the current user has admin privileges.
    Used for maintenance, monitoring, and other administrative endpoints.

    Raises:
        UnauthorizedError: If authentication fails.
        HTTPException: 403 Forbidden if user is not admin.
    """
    from app.core.prometheus_metrics import admin_unauthorized_access_total

    settings = get_settings()

    # If auth_provider is 'none', return anonymous admin user (development only)
    if settings.auth_provider == "none":
        return User(
            id="anonymous",
            fullname="anonymous",
            email="anonymous@localhost",
            role=UserRole.ADMIN,
            is_active=True,
        )

    # Check if bearer token is provided
    if not bearer_credentials:
        _raise_auth_error("auth_required")

    try:
        # Verify bearer token with blacklist + revocation checks
        user, reason = await _verify_token_with_reason(auth_service, bearer_credentials.credentials)

        if not user:
            _raise_auth_error(reason)

        if not user.is_active:
            _raise_auth_error("user_inactive")

        # Check admin role
        if user.role != UserRole.ADMIN:
            admin_unauthorized_access_total.inc({"endpoint": "admin"})
            logger.warning(
                "[SECURITY] Non-admin user %s (%s) attempted to access admin endpoint",
                user.id,
                user.email,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
            )

        return user

    except HTTPException:
        raise
    except UnauthorizedError:
        raise
    except Exception as e:
        logger.warning(f"Admin authentication failed: {e}")
        raise UnauthorizedError("Authentication failed") from e


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
        _raise_auth_error("auth_required")

    try:
        # Verify bearer token with blacklist + revocation checks
        user, reason = await _verify_token_with_reason(auth_service, bearer_credentials.credentials)

        if not user:
            _raise_auth_error(reason)

        if not user.is_active:
            _raise_auth_error("user_inactive")

        return user

    except UnauthorizedError:
        raise
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
        _raise_auth_error("auth_required")

    try:
        user, reason = await _verify_token_with_reason(auth_service, token)
        if not user:
            _raise_auth_error(reason)
        if not user.is_active:
            _raise_auth_error("user_inactive")
        return user
    except UnauthorizedError:
        raise
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
        # Try to verify bearer token with blacklist + revocation checks
        user = await auth_service.verify_token_secure(bearer_credentials.credentials)

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
    return query_params.get("uid", [None])[0]
