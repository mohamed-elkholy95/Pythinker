import hashlib
import hmac
import logging
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings
from app.core.prometheus_metrics import token_auth_fail_closed_total
from app.domain.models.user import User
from app.infrastructure.storage.redis import get_redis

logger = logging.getLogger(__name__)


class TokenService:
    """Token manager for authentication, token revocation, and URL signing"""

    # Redis key prefixes
    BLACKLIST_PREFIX = "token:blacklist:"
    USER_TOKENS_PREFIX = "token:user:"

    def __init__(self):
        self.settings = get_settings()

    @property
    def _refresh_secret(self) -> str:
        """Separate signing secret for refresh tokens. Falls back to main secret."""
        return self.settings.jwt_refresh_secret_key or self.settings.jwt_secret_key

    def create_access_token(self, user: User) -> str:
        """Create JWT access token for user"""
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=self.settings.jwt_access_token_expire_minutes)

        payload = {
            "sub": user.id,  # Subject (user ID)
            "fullname": user.fullname,
            "email": user.email,
            "role": user.role.value,
            "is_active": user.is_active,
            "iat": int(now.timestamp()),  # Issued at (timestamp)
            "exp": int(expire.timestamp()),  # Expiration time (timestamp)
            "type": "access",
        }

        try:
            token = jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_algorithm)
            logger.debug(f"Created access token for user: {user.fullname}")
            return token
        except Exception as e:
            logger.error(f"Failed to create access token: {e}")
            raise

    def create_refresh_token(self, user: User) -> str:
        """Create JWT refresh token for user (signed with separate refresh secret)"""
        now = datetime.now(UTC)
        expire = now + timedelta(days=self.settings.jwt_refresh_token_expire_days)

        payload = {
            "sub": user.id,  # Subject (user ID)
            "fullname": user.fullname,
            "iat": int(now.timestamp()),  # Issued at (timestamp)
            "exp": int(expire.timestamp()),  # Expiration time (timestamp)
            "type": "refresh",
        }

        try:
            token = jwt.encode(payload, self._refresh_secret, algorithm=self.settings.jwt_algorithm)
            logger.debug(f"Created refresh token for user: {user.fullname}")
            return token
        except Exception as e:
            logger.error(f"Failed to create refresh token: {e}")
            raise

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify JWT token and return payload"""
        payload, _ = self.verify_token_with_reason(token)
        return payload

    def verify_token_with_reason(
        self, token: str, *, expected_type: str | None = None
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Verify JWT token and return payload plus machine-readable failure reason.

        Args:
            token: The JWT token string.
            expected_type: If set, only accept tokens of this type ("access" or "refresh").
                           Refresh tokens are verified against the refresh secret.
        """
        # Choose signing secret: refresh tokens use _refresh_secret
        secret = self._refresh_secret if expected_type == "refresh" else self.settings.jwt_secret_key

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[self.settings.jwt_algorithm],
                leeway=5,
                options={"require": ["exp", "iat", "sub"]},
            )

            # Enforce token type if caller specified it
            if expected_type and payload.get("type") != expected_type:
                logger.warning("Token type mismatch: expected %s, got %s", expected_type, payload.get("type"))
                return None, "invalid_token"

            logger.debug(f"Token verified for user: {payload.get('fullname')}")
            return payload, None

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None, "token_expired"
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None, "invalid_token"
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None, "token_verification_failed"

    async def verify_token_async(self, token: str, *, expected_type: str | None = None) -> dict[str, Any] | None:
        """Verify JWT token with blacklist and user revocation check (async version)"""
        payload, _ = await self.verify_token_async_with_reason(token, expected_type=expected_type)
        return payload

    async def verify_token_async_with_reason(
        self, token: str, *, expected_type: str | None = None
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Verify JWT token and include a machine-readable failure reason."""
        # First do basic JWT verification
        payload, reason = self.verify_token_with_reason(token, expected_type=expected_type)
        if not payload:
            return None, reason

        # Check if token is blacklisted
        if self.settings.jwt_token_blacklist_enabled and await self._is_token_blacklisted(token):
            logger.warning("Token is blacklisted")
            return None, "token_revoked"

        # Check if all user tokens were revoked (logout-all-devices)
        user_id = payload.get("sub")
        issued_at = payload.get("iat")
        if user_id and issued_at and await self.is_user_token_revoked(str(user_id), issued_at):
            logger.warning(f"Token revoked for user: {user_id}")
            return None, "token_revoked"

        return payload, None

    async def _is_token_blacklisted(self, token: str) -> bool:
        """Check if token is in the blacklist.

        Security: Fails CLOSED on Redis errors. If the blacklist cannot be
        checked (e.g. Redis unavailable), the token is treated as blacklisted
        and access is denied. This prevents revoked or compromised tokens from
        being accepted during infrastructure outages.
        """
        try:
            redis = get_redis()
            token_hash = self._hash_token(token)
            key = f"{self.BLACKLIST_PREFIX}{token_hash}"
            return await redis.call("exists", key) > 0
        except Exception as e:
            token_hash = self._hash_token(token)
            logger.error(
                "Token blacklist check failed - FAILING CLOSED (denying access)",
                exc_info=e,
                extra={"token_hash_prefix": token_hash[:8]},
            )
            token_auth_fail_closed_total.inc({"check_type": "blacklist"})
            # Fail closed: deny access when blacklist cannot be verified
            return True

    def _hash_token(self, token: str) -> str:
        """Hash token for storage (don't store raw tokens)"""
        return hashlib.sha256(token.encode()).hexdigest()[:32]

    def _get_token_ttl(self, token: str, *, secret: str | None = None) -> int:
        """Get remaining TTL for token in seconds.

        Args:
            token: The JWT token string.
            secret: Signing secret to use for decoding. Defaults to jwt_secret_key.
                    Pass _refresh_secret for refresh tokens.
        """
        try:
            payload = jwt.decode(
                token,
                secret or self.settings.jwt_secret_key,
                algorithms=[self.settings.jwt_algorithm],
                options={"verify_exp": False},  # Don't verify expiry for TTL calculation
            )
            exp = payload.get("exp")
            if exp:
                remaining = exp - int(datetime.now(UTC).timestamp())
                return max(remaining, 0)
        except Exception as e:
            logger.debug(f"Token TTL calculation failed: {e}")
        return 0

    def get_user_from_token(self, token: str) -> dict[str, Any] | None:
        """Extract user information from JWT token"""
        payload = self.verify_token(token)

        if not payload:
            return None

        # Return user info from token payload
        return {
            "id": payload.get("sub"),
            "fullname": payload.get("fullname"),
            "email": payload.get("email"),
            "role": payload.get("role"),
            "is_active": payload.get("is_active", True),
            "token_type": payload.get("type", "access"),
        }

    def is_token_valid(self, token: str) -> bool:
        """Check if token is valid"""
        return self.verify_token(token) is not None

    def get_token_expiration(self, token: str) -> datetime | None:
        """Get token expiration time"""
        payload = self.verify_token(token)
        if not payload:
            return None

        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(exp, UTC)
        return None

    def create_resource_access_token(
        self, resource_type: str, resource_id: str, user_id: str, expire_minutes: int = 60
    ) -> str:
        """Create JWT resource access token for URL-based access

        Args:
            resource_type: Type of resource (file, screencast/input stream, etc.)
            resource_id: ID of the resource (file_id, session_id, etc.)
            user_id: User ID who requested the token
            expire_minutes: Token expiration time in minutes
        """
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=expire_minutes)

        payload = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_id": user_id,
            "iat": int(now.timestamp()),  # Issued at (timestamp)
            "exp": int(expire.timestamp()),  # Expiration time (timestamp)
            "type": "resource_access",
        }

        try:
            token = jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_algorithm)
            logger.debug(f"Created resource access token for {resource_type}: {resource_id}, user: {user_id}")
            return token
        except Exception as e:
            logger.error(f"Failed to create resource access token: {e}")
            raise

    def revoke_token(self, token: str) -> bool:
        """Synchronous token revocation - use revoke_token_async for proper implementation"""
        logger.warning("Synchronous revoke_token called - token may not be properly revoked")
        return True

    async def revoke_token_async(self, token: str) -> bool:
        """
        Revoke a token by adding it to the blacklist.
        The blacklist entry expires when the token would have expired.
        """
        if not self.settings.jwt_token_blacklist_enabled:
            logger.debug("Token blacklist disabled - skipping revocation")
            return True

        try:
            redis = get_redis()
            token_hash = self._hash_token(token)
            key = f"{self.BLACKLIST_PREFIX}{token_hash}"

            # Get remaining TTL for the token
            ttl = self._get_token_ttl(token)
            if ttl <= 0:
                # Token already expired, no need to blacklist
                logger.debug("Token already expired - no need to blacklist")
                return True

            # Add to blacklist with expiry matching token expiry
            await redis.call("setex", key, ttl, "revoked")
            logger.info(f"Token revoked and blacklisted (TTL: {ttl}s)")
            return True

        except Exception as e:
            logger.error(f"Failed to revoke token: {e}")
            return False

    async def blacklist_refresh_token(self, token: str) -> bool:
        """Blacklist a used refresh token to prevent replay attacks.

        The blacklist entry expires when the token would have expired,
        so storage is bounded and self-cleaning.
        """
        if not self.settings.jwt_token_blacklist_enabled:
            logger.debug("Token blacklist disabled - skipping refresh token blacklist")
            return True

        try:
            redis = get_redis()
            token_hash = self._hash_token(token)
            key = f"{self.BLACKLIST_PREFIX}{token_hash}"

            # Use refresh secret for TTL calculation since this is a refresh token
            ttl = self._get_token_ttl(token, secret=self._refresh_secret)
            if ttl <= 0:
                logger.debug("Refresh token already expired - no need to blacklist")
                return True

            await redis.call("setex", key, ttl, "rotated")
            logger.debug("Used refresh token blacklisted (TTL: %ds)", ttl)
            return True

        except Exception as e:
            logger.error("Failed to blacklist refresh token: %s", e)
            return False

    async def revoke_all_user_tokens(self, user_id: str) -> bool:
        """
        Revoke all tokens for a user by tracking a 'revoked_before' timestamp.
        Any token issued before this timestamp is considered invalid.
        """
        if not self.settings.jwt_token_blacklist_enabled:
            return True

        try:
            redis = get_redis()
            key = f"{self.USER_TOKENS_PREFIX}{user_id}:revoked_before"

            # Set the current timestamp - all tokens issued before this are invalid
            timestamp = int(datetime.now(UTC).timestamp())

            # Keep this for the max token lifetime (refresh token duration)
            max_ttl = self.settings.jwt_refresh_token_expire_days * 24 * 60 * 60
            await redis.call("setex", key, max_ttl, str(timestamp))

            logger.info(f"All tokens revoked for user: {user_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to revoke all user tokens: {e}")
            return False

    async def is_user_token_revoked(self, user_id: str, issued_at: int) -> bool:
        """Check if a user's token was issued before the revocation timestamp.

        Security: Fails CLOSED on Redis errors. If the revocation status cannot
        be checked (e.g. Redis unavailable), the token is treated as revoked and
        access is denied. This prevents tokens that should have been invalidated
        (e.g. after password change or logout-all) from being accepted during
        infrastructure outages.
        """
        if not self.settings.jwt_token_blacklist_enabled:
            return False

        try:
            redis = get_redis()
            key = f"{self.USER_TOKENS_PREFIX}{user_id}:revoked_before"

            revoked_before = await redis.call("get", key)
            if revoked_before:
                return issued_at < int(revoked_before)
            return False

        except Exception as e:
            logger.error(
                "User token revocation check failed - FAILING CLOSED (denying access)",
                exc_info=e,
                extra={"user_id": user_id},
            )
            token_auth_fail_closed_total.inc({"check_type": "user_revocation"})
            # Fail closed: deny access when revocation status cannot be verified
            return True

    def create_signed_url(self, base_url: str, expire_minutes: int = 60, user_id: str | None = None) -> str:
        """Create URL with signature for resource access

        Args:
            base_url: Base URL for the resource (e.g., '/api/v1/files/123' or '/api/v1/sessions/456/screencast')
            expire_minutes: URL expiration time in minutes
            user_id: Optional user ID to bind the URL to (prevents URL sharing across users)

        Returns:
            Signed URL with signature and expiration parameters
        """
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=expire_minutes)
        expires_timestamp = int(expire.timestamp())

        final_url = base_url

        # Include user_id in HMAC payload when provided (user-bound URLs)
        payload_data = f"{final_url}|{expires_timestamp}|{user_id}" if user_id else f"{final_url}|{expires_timestamp}"

        # Generate HMAC signature
        signature = hmac.new(
            self.settings.jwt_secret_key.encode("utf-8"), payload_data.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Parse URL to add query parameters
        parsed_url = urllib.parse.urlparse(final_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # Add signature parameters
        query_params["signature"] = [signature]
        query_params["expires"] = [str(expires_timestamp)]
        if user_id:
            query_params["uid"] = [user_id]

        # Rebuild URL with signature parameters
        new_query = urllib.parse.urlencode(query_params, doseq=True)
        signed_url = urllib.parse.urlunparse(
            ("", "", parsed_url.path, parsed_url.params, new_query, parsed_url.fragment)
        )

        logger.debug("Created signed URL for: %s (user_bound=%s)", final_url, bool(user_id))
        return signed_url

    def verify_signed_url(self, request_url: str) -> bool:
        """Verify signed URL

        Args:
            request_url: Full request URL with query parameters

        Returns:
            True if valid, False if invalid
        """
        try:
            # Redact signature from log output to prevent token leakage
            parsed_for_log = urllib.parse.urlparse(request_url)
            log_path = parsed_for_log.path
            logger.debug("Verifying signed URL for path: %s", log_path)

            # Parse URL and extract query parameters
            parsed_url = urllib.parse.urlparse(request_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)

            # Extract required parameters
            signature = query_params.get("signature", [None])[0]
            expires_str = query_params.get("expires", [None])[0]
            user_id = query_params.get("uid", [None])[0]

            if not all([signature, expires_str]):
                logger.warning("Missing required signature parameters in URL")
                return False

            # Check expiration
            expires_timestamp = int(expires_str)
            if expires_timestamp < int(datetime.now(UTC).timestamp()):
                logger.warning("Signed URL has expired")
                return False

            # Reconstruct base URL without signature parameters
            base_query_params = {k: v for k, v in query_params.items() if k not in ["signature", "expires", "uid"]}
            base_query = urllib.parse.urlencode(base_query_params, doseq=True)
            base_url = urllib.parse.urlunparse(
                ("", "", parsed_url.path, parsed_url.params, base_query, parsed_url.fragment)
            )

            # Recreate payload for signature verification (include user_id if present)
            payload_data = f"{base_url}|{expires_timestamp}|{user_id}" if user_id else f"{base_url}|{expires_timestamp}"

            # Generate expected signature
            expected_signature = hmac.new(
                self.settings.jwt_secret_key.encode("utf-8"), payload_data.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            # Compare signatures using constant-time comparison to prevent timing attacks
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Invalid signature in signed URL")
                return False

            logger.debug("Signed URL verified for: %s", log_path)
            return True

        except Exception as e:
            logger.error(f"Signed URL verification failed: {e}")
            return False
