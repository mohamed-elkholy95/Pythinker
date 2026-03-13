from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ORIGINS: List[str] = ["*"]

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

    # API authentication — shared secret with backend
    # When set, all /api/v1/* requests must include X-Sandbox-Secret header
    SANDBOX_API_SECRET: Optional[str] = None

    # Supervisord XML-RPC auth (unix_http_server/supervisorctl).
    SUPERVISOR_RPC_USERNAME: str = "supervisor"
    SUPERVISOR_RPC_PASSWORD: str = "supervisor-dev-password"

    # Log configuration
    LOG_LEVEL: str = "INFO"

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

    @field_validator("ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
