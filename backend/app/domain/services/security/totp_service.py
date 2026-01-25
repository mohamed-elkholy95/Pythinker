"""
TOTP (Time-based One-Time Password) service.

Provides TOTP secret generation, code generation, and verification
for 2FA/MFA support in the credential management system.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import pyotp
try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False
    logger.warning("pyotp package not installed. TOTP functionality will be disabled.")


class TOTPService:
    """
    TOTP (Time-based One-Time Password) service.

    Provides standard TOTP operations compatible with common authenticator apps
    (Google Authenticator, Authy, Microsoft Authenticator, etc.).

    Default configuration:
    - SHA1 algorithm (standard)
    - 6 digits
    - 30 second period
    """

    @staticmethod
    def is_available() -> bool:
        """Check if TOTP functionality is available (pyotp installed)."""
        return PYOTP_AVAILABLE

    @staticmethod
    def generate_secret(length: int = 32) -> str:
        """
        Generate a new TOTP secret (Base32 encoded).

        Args:
            length: Length of the secret in bytes (default: 32)

        Returns:
            Base32-encoded secret string suitable for storage

        Raises:
            RuntimeError: If pyotp is not available
        """
        if not PYOTP_AVAILABLE:
            raise RuntimeError("pyotp package not installed")
        return pyotp.random_base32(length)

    @staticmethod
    def get_current_code(
        totp_secret: str,
        digits: int = 6,
        period: int = 30,
    ) -> str:
        """
        Get the current TOTP code for a secret.

        Args:
            totp_secret: Base32-encoded TOTP secret
            digits: Number of digits in the code (default: 6)
            period: Time period in seconds (default: 30)

        Returns:
            Current TOTP code as string (zero-padded)

        Raises:
            RuntimeError: If pyotp is not available
            ValueError: If the secret is invalid
        """
        if not PYOTP_AVAILABLE:
            raise RuntimeError("pyotp package not installed")

        try:
            totp = pyotp.TOTP(totp_secret, digits=digits, interval=period)
            return totp.now()
        except Exception as e:
            logger.error(f"Failed to generate TOTP code: {e}")
            raise ValueError(f"Invalid TOTP secret: {e}")

    @staticmethod
    def verify_code(
        totp_secret: str,
        code: str,
        digits: int = 6,
        period: int = 30,
        window: int = 1,
    ) -> bool:
        """
        Verify a TOTP code with time window tolerance.

        The window parameter allows for clock drift between client and server.
        A window of 1 means the code from the previous and next period are
        also accepted.

        Args:
            totp_secret: Base32-encoded TOTP secret
            code: Code to verify
            digits: Number of digits in the code (default: 6)
            period: Time period in seconds (default: 30)
            window: Number of periods to check before/after current (default: 1)

        Returns:
            True if code is valid, False otherwise

        Raises:
            RuntimeError: If pyotp is not available
        """
        if not PYOTP_AVAILABLE:
            raise RuntimeError("pyotp package not installed")

        try:
            totp = pyotp.TOTP(totp_secret, digits=digits, interval=period)
            return totp.verify(code, valid_window=window)
        except Exception as e:
            logger.error(f"Failed to verify TOTP code: {e}")
            return False

    @staticmethod
    def get_provisioning_uri(
        secret: str,
        account: str,
        issuer: str = "Pythinker",
        digits: int = 6,
        period: int = 30,
    ) -> str:
        """
        Get the provisioning URI for authenticator app setup.

        This URI can be converted to a QR code that users scan with their
        authenticator app to set up 2FA.

        Args:
            secret: Base32-encoded TOTP secret
            account: Account name/email (displayed in authenticator app)
            issuer: Service name (displayed in authenticator app)
            digits: Number of digits in the code (default: 6)
            period: Time period in seconds (default: 30)

        Returns:
            otpauth:// URI string for QR code generation

        Raises:
            RuntimeError: If pyotp is not available
        """
        if not PYOTP_AVAILABLE:
            raise RuntimeError("pyotp package not installed")

        totp = pyotp.TOTP(secret, digits=digits, interval=period)
        return totp.provisioning_uri(name=account, issuer_name=issuer)

    @staticmethod
    def get_time_remaining(period: int = 30) -> int:
        """
        Get the seconds remaining until the current TOTP code expires.

        Useful for displaying a countdown timer in the UI.

        Args:
            period: Time period in seconds (default: 30)

        Returns:
            Seconds remaining until current code expires
        """
        import time
        return period - (int(time.time()) % period)


# Singleton instance for convenience
_totp_service: Optional[TOTPService] = None


def get_totp_service() -> TOTPService:
    """Get the global TOTP service singleton."""
    global _totp_service
    if _totp_service is None:
        _totp_service = TOTPService()
    return _totp_service
