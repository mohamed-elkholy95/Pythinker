"""Security Headers Middleware

Context7 Validated: FastAPI security best practices
Adds production-grade security headers to all responses.

Security headers implemented:
- HSTS (HTTP Strict Transport Security)
- CSP (Content Security Policy)
- X-Frame-Options (Clickjacking protection)
- X-Content-Type-Options (MIME sniffing protection)
- X-XSS-Protection (XSS protection - legacy browsers)
- Referrer-Policy (Privacy protection)
- Permissions-Policy (Feature policy)
"""

import logging
from collections.abc import Callable
from typing import ClassVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all HTTP responses

    Context7 Best Practice: Always include security headers in production
    applications to protect against common web vulnerabilities.

    References:
    - OWASP Secure Headers Project
    - Mozilla Web Security Guidelines
    - FastAPI security documentation
    """

    # Paths that don't need strict CSP (e.g., API docs)
    RELAXED_CSP_PATHS: ClassVar[set[str]] = {"/docs", "/redoc", "/openapi.json"}

    def __init__(self, app: Callable):
        super().__init__(app)
        # Resolve settings in __init__ (not at module import time) so that
        # test overrides and runtime environment changes are always respected
        # (IMPORTANT-1).
        self._settings = get_settings()
        self._headers = self._build_security_headers()
        logger.info(f"SecurityHeadersMiddleware initialized (environment: {self._settings.environment})")

    def _build_security_headers(self) -> dict[str, str]:
        """Build security headers based on environment configuration"""
        headers = {}

        # === HSTS (HTTP Strict Transport Security) ===
        # Force HTTPS for 1 year (31536000 seconds)
        # Context7: Enable only in production with HTTPS
        if self._settings.is_production:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # === Content Security Policy (CSP) ===
        # Restrict resource loading to prevent XSS attacks
        # Context7: Strict policy for production, relaxed for development
        if self._settings.is_production:
            # Production: Strict CSP
            csp_directives = [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline'",  # Allow inline styles for UI frameworks
                "img-src 'self' data: https:",
                "font-src 'self' data:",
                "connect-src 'self' wss:",
                "frame-ancestors 'none'",  # Prevent embedding
                "base-uri 'self'",
                "form-action 'self'",
            ]
        else:
            # Development: Relaxed CSP for local development
            csp_directives = [
                "default-src 'self' 'unsafe-inline' 'unsafe-eval'",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https: http:",
                "connect-src 'self' ws: wss: http: https:",  # Allow WebSocket for hot reload
            ]

        headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # === X-Frame-Options ===
        # Prevent clickjacking attacks
        # Context7: DENY prevents any framing, SAMEORIGIN allows same-origin framing
        headers["X-Frame-Options"] = "DENY"

        # === X-Content-Type-Options ===
        # Prevent MIME sniffing
        # Context7: Always set to 'nosniff' to prevent browser MIME-type confusion
        headers["X-Content-Type-Options"] = "nosniff"

        # === X-XSS-Protection ===
        # Legacy XSS protection for older browsers
        # Context7: Set to '1; mode=block' for legacy browser support
        headers["X-XSS-Protection"] = "1; mode=block"

        # === Referrer-Policy ===
        # Control referrer information sent with requests
        # Context7: 'strict-origin-when-cross-origin' balances privacy and functionality
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # === Permissions-Policy (formerly Feature-Policy) ===
        # Restrict browser features
        # Context7: Disable potentially dangerous features by default
        permissions = [
            "camera=()",
            "microphone=()",
            "geolocation=()",
            "payment=()",
            "usb=()",
            "magnetometer=()",
        ]
        headers["Permissions-Policy"] = ", ".join(permissions)

        # === X-Permitted-Cross-Domain-Policies ===
        # Restrict Adobe Flash and PDF cross-domain access
        headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # === Cache-Control (for sensitive endpoints) ===
        # Set in path-specific logic below
        # Context7: Use 'no-store' for sensitive data, 'public, max-age=...' for static assets

        return headers

    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to response"""
        response = await call_next(request)

        # Add standard security headers
        for header, value in self._headers.items():
            response.headers[header] = value

        # === Path-Specific Headers ===

        path = request.url.path

        # Relax CSP for API documentation endpoints
        if path in self.RELAXED_CSP_PATHS:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "img-src 'self' data: https:; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;"
            )

        # Strict cache control for auth endpoints
        if "/auth/" in path or "/sessions/" in path:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        # Public cache for static assets (health checks, public endpoints)
        elif path in {"/health", "/health/live", "/health/ready"}:
            response.headers["Cache-Control"] = "public, max-age=60"

        return response


def add_security_headers_middleware(app) -> None:
    """Register security headers middleware to FastAPI app

    Usage:
        from app.infrastructure.middleware.security_headers import add_security_headers_middleware

        app = FastAPI()
        add_security_headers_middleware(app)

    Context7 Best Practice: Add security middleware early in the middleware stack
    to ensure all responses include security headers.
    """
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security headers middleware registered")
