"""Stealth and anti-detection configuration mixin.

Follows the codebase mixin pattern: plain class with typed attributes,
composed into Settings via multiple inheritance (config.py).
"""

from pydantic import Field, computed_field


class StealthSettingsMixin:
    """Configuration for stealth browser operations."""

    # Cloudflare bypass
    stealth_cloudflare_enabled: bool = Field(
        default=True,
        description="Enable Cloudflare challenge solving",
    )
    stealth_cloudflare_timeout: int = Field(
        default=60,
        ge=30,
        le=180,
        description="Timeout in seconds for Cloudflare challenge solving",
    )

    # Fingerprint hardening
    stealth_canvas_noise: bool = Field(
        default=True,
        description="Add random noise to canvas operations to prevent fingerprinting",
    )
    stealth_webgl_enabled: bool = Field(
        default=True,
        description="Keep WebGL enabled (disabling triggers WAF detection)",
    )
    stealth_webrtc_block: bool = Field(
        default=True,
        description="Block WebRTC to prevent local IP leak",
    )
    stealth_google_referer: bool = Field(
        default=True,
        description="Set referer to appear from Google search (Scrapling default)",
    )

    # Proxy rotation
    stealth_proxy_enabled: bool = Field(
        default=False,
        description="Enable proxy rotation",
    )
    stealth_proxy_list: str = Field(
        default="",
        description="Comma-separated proxy URLs (http://user:pass@host:port)",
    )
    stealth_proxy_health_check_enabled: bool = Field(
        default=True,
        description="Enable periodic proxy health checks",
    )
    stealth_proxy_health_check_interval: int = Field(
        default=300,
        ge=60,
        description="Health check interval in seconds",
    )
    stealth_proxy_max_failures: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max failures before marking proxy unhealthy",
    )

    # Session management
    stealth_session_max_pages: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max concurrent tabs per session (Scrapling max_pages param)",
    )
    stealth_session_timeout: int = Field(
        default=30000,
        ge=5000,
        le=120000,
        description="Session timeout in milliseconds",
    )
    stealth_session_network_idle: bool = Field(
        default=True,
        description="Wait for network idle before returning",
    )
    stealth_session_idle_cleanup_enabled: bool = Field(
        default=True,
        description="Enable cleanup of idle sessions",
    )
    stealth_session_idle_cleanup_interval: int = Field(
        default=60,
        ge=30,
        description="Cleanup check interval in seconds",
    )
    stealth_session_idle_threshold_seconds: int = Field(
        default=300,
        ge=60,
        description="Idle threshold before session cleanup",
    )

    # Resource blocking for performance
    stealth_disable_resources: bool = Field(
        default=False,
        description="Enable Scrapling's broad non-essential resource blocking flag",
    )

    @computed_field
    @property
    def has_stealth_proxies(self) -> bool:
        """Check if any stealth proxies are configured."""

        return any(proxy.strip() for proxy in self.stealth_proxy_list.split(","))
