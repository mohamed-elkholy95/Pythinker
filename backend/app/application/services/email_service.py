import json
import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.application.errors.exceptions import BadRequestError
from app.core.config import get_settings
from app.domain.external.cache import Cache

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for sending verification codes and notifications"""

    # Class variables
    VERIFICATION_CODE_PREFIX = "verification_code:"
    VERIFICATION_CODE_EXPIRY_SECONDS = 300  # 5 minutes

    def __init__(self, cache: Cache):
        self.settings = get_settings()
        self.cache = cache

    def _generate_verification_code(self) -> str:
        """Generate 6-digit verification code using cryptographically secure random"""
        return f"{secrets.randbelow(900000) + 100000}"

    async def _store_verification_code(self, email: str, code: str) -> None:
        """Store verification code with expiration time in cache"""
        now = datetime.now()
        # Create verification code data
        code_data = {
            "code": code,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.VERIFICATION_CODE_EXPIRY_SECONDS)).isoformat(),
            "attempts": 0,
        }

        # Store in cache with TTL
        key = f"{self.VERIFICATION_CODE_PREFIX}{email}"
        await self.cache.set(key, code_data, ttl=self.VERIFICATION_CODE_EXPIRY_SECONDS)

    async def verify_code(self, email: str, code: str) -> bool:
        """Verify if the provided code is valid for the email"""
        key = f"{self.VERIFICATION_CODE_PREFIX}{email}"

        # Get stored data from cache
        stored_data = await self.cache.get(key)
        if not stored_data:
            return False

        # Check if code has expired (cache TTL should handle this, but double-check)
        expires_at = datetime.fromisoformat(stored_data["expires_at"])
        if datetime.now() > expires_at:
            await self.cache.delete(key)
            return False

        # Check attempts limit (max 3 attempts)
        if stored_data["attempts"] >= 3:
            await self.cache.delete(key)
            return False

        # Increment attempt count
        stored_data["attempts"] += 1

        # Check if code matches
        if stored_data["code"] == code:
            # Remove the code after successful verification
            await self.cache.delete(key)
            return True

        # Update attempt count in cache
        remaining_ttl = int((expires_at - datetime.now()).total_seconds())
        if remaining_ttl > 0:
            await self.cache.set(key, stored_data, ttl=remaining_ttl)

        return False

    def _create_verification_email(self, email: str, code: str) -> MIMEMultipart:
        """Create verification email content"""
        msg = MIMEMultipart()
        msg["From"] = self.settings.email_from or self.settings.email_username
        msg["To"] = email
        msg["Subject"] = "Password Reset Verification Code"

        # Email body
        body = f"""
        <html>
        <body>
            <h2>Password Reset Verification</h2>
            <p>You have requested to reset your password. Please use the following verification code:</p>
            <h3 style="color: #007bff; font-size: 24px; letter-spacing: 2px;">{code}</h3>
            <p><strong>This code will expire in 5 minutes.</strong></p>
            <p>If you did not request this password reset, please ignore this email.</p>
            <br>
            <p>Best regards,<br>AI Manus Team</p>
        </body>
        </html>
        """

        msg.attach(MIMEText(body, "html"))
        return msg

    async def send_verification_code(self, email: str):
        """Send verification code to email address"""
        # Check if email configuration is available
        if not all(
            [
                self.settings.email_host,
                self.settings.email_port,
                self.settings.email_username,
                self.settings.email_password,
            ]
        ):
            logger.error("Email configuration is incomplete, simulating email send")
            raise BadRequestError("Email configuration is incomplete")

        # Check if there's an existing verification code that's too recent
        key = f"{self.VERIFICATION_CODE_PREFIX}{email}"
        existing_data = await self.cache.get(key)
        if existing_data:
            try:
                # Check if the existing code was created less than 60 seconds ago
                created_at = datetime.fromisoformat(existing_data["created_at"])
                time_since_creation = (datetime.now() - created_at).total_seconds()

                if time_since_creation < 60:
                    remaining_wait = int(60 - time_since_creation)
                    raise BadRequestError(
                        f"Please wait {remaining_wait} seconds before requesting a new verification code"
                    )
            except (KeyError, ValueError):
                # Invalid data, continue with new code generation
                pass

        # Generate verification code
        code = self._generate_verification_code()
        logger.debug(f"Generated verification code: {code}")

        # Create email message
        msg = self._create_verification_email(email, code)
        logger.debug(f"Created email message: {msg}")

        # Send email using SMTP
        await self._send_smtp_email(msg, email)

        # Store verification code
        await self._store_verification_code(email, code)

        logger.info(f"Verification code sent to {email}")

    async def _send_smtp_email(self, msg: MIMEMultipart, email: str) -> None:
        """Send email using SMTP (runs in thread pool to avoid blocking)"""
        logger.debug(f"Sending email to {email}")
        server = None
        try:
            # Create SMTP server connection
            logger.debug(f"Creating SMTP server connection to {self.settings.email_host}:{self.settings.email_port}")
            server = smtplib.SMTP_SSL(self.settings.email_host, self.settings.email_port)
            logger.debug(f"SMTP server created, {server}")
            result = server.login(self.settings.email_username, self.settings.email_password)
            logger.debug(f"SMTP server login result: {result}")

            # Send email
            text = msg.as_string()
            result = server.sendmail(msg["From"], email, text)
            logger.debug(f"SMTP server sendmail result: {result}")
        finally:
            if server:
                server.quit()

    async def send_rating_email(
        self,
        *,
        user_email: str,
        user_name: str,
        session_id: str,
        report_id: str,
        rating: int,
        feedback: str | None = None,
    ) -> None:
        """Send rating notification email with structured JSON data."""
        target = self.settings.rating_notification_email
        if not target:
            logger.debug("No rating_notification_email configured, skipping")
            return

        if not all(
            [
                self.settings.email_host,
                self.settings.email_port,
                self.settings.email_username,
                self.settings.email_password,
            ]
        ):
            logger.debug("Email config incomplete, skipping rating email")
            return

        stars = "\u2605" * rating + "\u2606" * (5 - rating)
        rating_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "user_email": user_email,
            "user_name": user_name,
            "session_id": session_id,
            "report_id": report_id,
            "rating": rating,
            "rating_display": stars,
            "feedback": feedback,
        }

        msg = MIMEMultipart()
        msg["From"] = self.settings.email_from or self.settings.email_username
        msg["To"] = target
        msg["Subject"] = f"Pythinker Rating: {stars} ({rating}/5) from {user_name}"

        json_str = json.dumps(rating_data, indent=2, ensure_ascii=False)
        body = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #333;">
            <h2 style="margin-bottom: 4px;">Session Rating: {stars}</h2>
            <p style="color: #666; margin-top: 0;">
                <strong>{user_name}</strong> ({user_email}) rated <strong>{rating}/5</strong>
            </p>
            {f'<p style="background: #f5f5f5; padding: 12px; border-radius: 8px; border-left: 3px solid #3b82f6;">{feedback}</p>' if feedback else ""}
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
            <details>
                <summary style="cursor: pointer; color: #888; font-size: 13px;">JSON Data</summary>
                <pre style="background: #f8f8f8; padding: 12px; border-radius: 8px; font-size: 12px; overflow-x: auto;">{json_str}</pre>
            </details>
            <p style="color: #aaa; font-size: 11px; margin-top: 20px;">Pythinker Rating System</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html"))

        try:
            await self._send_smtp_email(msg, target)
            logger.info("Rating email sent to %s for session %s", target, session_id)
        except Exception:
            logger.exception("Failed to send rating email")

    async def cleanup_expired_codes(self) -> None:
        """Clean up expired verification codes - Cache TTL handles this automatically"""
        # Cache automatically handles expiration via TTL, so this method is mainly for manual cleanup

        # Get all verification code keys
        pattern = f"{self.VERIFICATION_CODE_PREFIX}*"
        keys = await self.cache.keys(pattern)

        expired_count = 0
        for key in keys:
            data = await self.cache.get(key)
            if data:
                try:
                    expires_at = datetime.fromisoformat(data["expires_at"])
                    if datetime.now() > expires_at:
                        await self.cache.delete(key)
                        expired_count += 1
                except (KeyError, ValueError):
                    # Invalid data, delete it
                    await self.cache.delete(key)
                    expired_count += 1

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired verification codes")
