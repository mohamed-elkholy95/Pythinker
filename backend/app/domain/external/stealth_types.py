"""Domain types for stealth browser operations.

These are domain-level value objects used across the stealth subsystem.
ProxyHealth uses Pydantic BaseModel for validation at boundaries.
FetchOptions/FetchResult use TypedDict for lightweight internal passing.
"""

from __future__ import annotations

from enum import Enum
from typing import TypedDict

from pydantic import BaseModel


class StealthMode(str, Enum):
    """Stealth operation modes in order of increasing sophistication."""

    HTTP = "http"
    DYNAMIC = "dynamic"
    STEALTH = "stealth"
    CLOUDFLARE = "cloudflare"


class ProxyStatus(str, Enum):
    """Health status of a proxy."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ProxyHealth(BaseModel):
    """Health information for a proxy."""

    proxy_url: str
    status: ProxyStatus = ProxyStatus.UNKNOWN
    success_count: int = 0
    failure_count: int = 0
    last_success: float | None = None
    last_failure: float | None = None
    last_error: str | None = None
    avg_response_time_ms: float | None = None


class FetchOptions(TypedDict, total=False):
    """Options for content fetching operations."""

    mode: StealthMode
    timeout_ms: int
    wait_selector: str | None
    wait_selector_state: str
    network_idle: bool
    proxy_id: str | None
    extra_headers: dict[str, str]
    disable_resources: bool


class FetchResult(TypedDict):
    """Result of a fetch operation with metadata."""

    content: str
    url: str
    final_url: str
    mode_used: StealthMode
    proxy_used: str | None
    response_time_ms: float
    from_cache: bool
    cloudflare_solved: bool
    error: str | None
