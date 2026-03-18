"""Authentication, authorization, and security settings mixins.

Contains configuration for auth provider, password hashing, account lockout,
email, JWT tokens, CORS, rate limiting, and metrics endpoint security.
"""


class AuthSettingsMixin:
    """Authentication provider and password policy configuration."""

    auth_provider: str = "password"  # "password", "none", "local"
    password_policy_version: int = 1
    password_salt: str | None = None
    password_hash_rounds: int = 600000  # OWASP recommendation for PBKDF2-SHA256
    password_hash_algorithm: str = "pbkdf2_sha256"
    password_min_length: int = 9  # Minimum password length
    password_max_length: int = 128  # Maximum password length
    password_require_uppercase: bool = True
    password_require_lowercase: bool = False
    password_require_digit: bool = False
    password_require_special: bool = True  # Require special character
    local_auth_email: str | None = None  # Must be set via environment
    local_auth_password: str | None = None  # Must be set via environment

    # Account lockout configuration
    account_lockout_enabled: bool = True
    account_lockout_threshold: int = 5  # Failed attempts before lockout
    account_lockout_duration_minutes: int = 15  # Lockout duration
    account_lockout_reset_minutes: int = 60  # Reset failed attempts counter after

    # Credential Manager Configuration (Enhancement Phase 2)
    credential_encryption_key: str | None = None  # AES-256 master key (32 bytes base64)
    credential_ttl_hours: int = 24  # Default credential TTL in Redis


class EmailSettingsMixin:
    """SMTP email configuration for notifications."""

    email_host: str | None = None  # "smtp.gmail.com"
    email_port: int | None = None  # 587
    email_username: str | None = None
    email_password: str | None = None
    email_from: str | None = None
    rating_notification_email: str | None = None


class JWTSettingsMixin:
    """JWT token configuration."""

    jwt_secret_key: str | None = None  # REQUIRED - must be set via environment
    jwt_refresh_secret_key: str | None = None  # Separate secret for refresh tokens (falls back to jwt_secret_key)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 20  # 20 minutes with proactive refresh
    jwt_refresh_token_expire_days: int = 7
    jwt_token_blacklist_enabled: bool = True  # Enable token revocation


class CORSSettingsMixin:
    """CORS and rate limiting configuration."""

    cors_origins: str = (
        ""  # Comma-separated list of allowed origins (e.g., "http://localhost:5173,https://app.example.com")
    )
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS,PATCH"
    cors_allow_headers: str = "Authorization,Content-Type,X-Request-ID"

    # Rate limiting configuration
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60  # Fixed window size for Redis-backed API rate limiting
    rate_limit_requests_per_minute: int = 300  # Increased for SSE polling (temporary)
    rate_limit_auth_requests_per_minute: int = 10  # Rate limit for auth endpoints (login, register)
    rate_limit_burst: int = 10  # Allow burst of requests


class MetricsAuthSettingsMixin:
    """Metrics endpoint authentication (HTTP Basic Auth for Prometheus scraping)."""

    metrics_username: str = "prometheus"
    metrics_password: str = ""  # REQUIRED in production - set METRICS_PASSWORD in .env
