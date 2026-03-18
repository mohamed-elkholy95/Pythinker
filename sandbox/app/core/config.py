import secrets as _secrets
from typing import List, Optional, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ORIGINS: List[str] = ["http://backend:8000", "http://localhost:8000"]

    # Service timeout settings (minutes)
    SERVICE_TIMEOUT_MINUTES: Optional[int] = None

    # Sandbox framework database (SQLite - lightweight, no separate process)
    FRAMEWORK_DATABASE_URL: str = (
        "sqlite+aiosqlite:////home/ubuntu/.local/pythinker_sandbox.db"
    )
    FRAMEWORK_DB_ECHO: bool = False

    # Security controls
    ALLOW_SUDO: bool = False
    SHELL_MAX_OUTPUT_CHARS: int = 200000
    SHELL_USE_STRUCTURED_MARKERS: bool = True

    # API authentication — shared secret with backend
    # When set, all /api/v1/* requests must include X-Sandbox-Secret header
    SANDBOX_API_SECRET: Optional[str] = None

    # Supervisord XML-RPC auth (unix_http_server/supervisorctl).
    SUPERVISOR_RPC_USERNAME: str = "supervisor"
    SUPERVISOR_RPC_PASSWORD: str = ""

    # Log configuration
    LOG_LEVEL: str = "INFO"

    # Deployment environment — controls security validation
    SANDBOX_ENVIRONMENT: str = "development"

    # ── CDP timeout constants ────────────────────────────────────────
    # Centralizes all CDP-related timeouts (previously scattered across
    # cdp_screencast.py, cdp_input.py, and screencast.py).
    # Override via environment variables for tuning.

    # WebSocket connection establishment timeout (seconds)
    CDP_CONNECT_TIMEOUT: float = 3.0
    # CDP command response timeout — used by both screencast and input services
    CDP_COMMAND_TIMEOUT: float = 6.0
    # Input dispatch command timeout — lighter than general commands
    CDP_INPUT_COMMAND_TIMEOUT: float = 5.0
    # Max seconds to wait for next screencast frame before declaring stream dead
    CDP_STREAM_FRAME_TIMEOUT: float = 10.0
    # Periodic health check interval during streaming (seconds)
    CDP_STREAM_HEALTH_CHECK_INTERVAL: float = 30.0
    # Cache TTL for WebSocket URL to avoid repeated /json lookups
    CDP_WS_URL_CACHE_TTL: float = 15.0
    # Screencast stream preemption wait timeout (must exceed CDP_COMMAND_TIMEOUT)
    CDP_PREEMPT_WAIT_TIMEOUT: float = 8.0

    # Environment metadata
    SANDBOX_VERSION: str = "dev"
    TZ: str = "UTC"

    # Screencast dimensions (Agent UX v2)
    SCREENCAST_INCLUDE_CHROME_UI: bool = True
    SCREENCAST_MAX_HEIGHT: int = (
        1024  # 1024 = full window with Chrome UI, 900 = viewport only
    )

    # Sandbox → Backend callback
    RUNTIME_API_HOST: Optional[str] = None
    RUNTIME_API_TOKEN: Optional[str] = None

    # LLM Proxy (OpenAI-compatible, provided by backend)
    OPENAI_API_BASE: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None

    # Code-Server (VS Code web IDE)
    CODE_SERVER_PORT: int = 8443
    CODE_SERVER_PASSWORD: Optional[str] = None
    ENABLE_CODE_SERVER: bool = False

    # Observability (OTEL + Sentry)
    OTEL_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_SERVICE_NAME: str = "sandbox-runtime"
    OTEL_TRACES_SAMPLER_RATIO: float = 1.0
    OTEL_BSP_MAX_EXPORT_BATCH_SIZE: int = 1024
    OTEL_BSP_SCHEDULE_DELAY: int = 10000
    OTEL_PYTHON_LOG_CORRELATION: bool = True
    OTEL_RESOURCE_ATTRIBUTES: str = "service.name=sandbox-runtime,service.env=sandbox"
    SENTRY_DSN: Optional[str] = None

    # Cloud service tokens
    GH_TOKEN: Optional[str] = None
    GOOGLE_DRIVE_TOKEN: Optional[str] = None
    GOOGLE_WORKSPACE_CLI_TOKEN: Optional[str] = None

    @field_validator("ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        """Refuse to start without SANDBOX_API_SECRET in non-development environments."""
        if self.SANDBOX_ENVIRONMENT != "development" and not self.SANDBOX_API_SECRET:
            raise ValueError(
                "SANDBOX_API_SECRET is required in production. "
                "Set it via environment variable to authenticate sandbox API requests."
            )
        return self

    @model_validator(mode="after")
    def generate_supervisor_password(self) -> "Settings":
        """Generate random supervisor password if not explicitly configured."""
        import logging
        if not self.SUPERVISOR_RPC_PASSWORD or self.SUPERVISOR_RPC_PASSWORD == "supervisor-dev-password":
            self.SUPERVISOR_RPC_PASSWORD = _secrets.token_urlsafe(24)
            logging.getLogger(__name__).warning(
                "SUPERVISOR_RPC_PASSWORD not set or using default — generated random password. "
                "Set SUPERVISOR_RPC_PASSWORD environment variable to use a fixed password."
            )
        return self

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
