import asyncio
import json
import logging
import secrets
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

from app.application.errors.exceptions import BadRequestError
from app.core.config import get_settings
from app.domain.external.cache import Cache

logger = logging.getLogger(__name__)

# Square icon served by the frontend at the public domain.
# Uses icon-192.png (192x192 square) instead of logo.png (822x1025 portrait)
# to avoid distortion when rendered at small sizes in email clients.
# Hosted URLs are the industry standard for email images:
# - data: URIs are blocked by Gmail/Outlook/Yahoo
# - CID attachments show a paperclip/attachment indicator in Gmail
# - Hosted URLs are proxied by Gmail (googleusercontent.com) for fast loading
_LOGO_URL = "https://pythinker.com/icon-192.png"


def _mask_email(email: str) -> str:
    """Mask email for safe logging: 'user@example.com' -> 'use***@example.com'."""
    local, _, domain = email.partition("@")
    return f"{local[:3]}***@{domain}" if domain else f"{email[:3]}***"


def _build_code_email_text(
    *,
    heading: str,
    intro: str,
    code: str,
    detail: str,
    ignore_note: str,
) -> str:
    return f"{heading}\n\n{intro}\n\nVerification code: {code}\n\n{detail}\n\n{ignore_note}\n\nPythinker"


def _build_code_email_html(
    *,
    eyebrow: str,
    heading: str,
    intro: str,
    code: str,
    detail: str,
    ignore_note: str,
) -> str:
    return f"""\
<html>
<body style="margin:0; padding:24px 12px; background:#eef4fb; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <div style="display:none; max-height:0; overflow:hidden; opacity:0; color:transparent;">
    {intro}
  </div>
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:560px; margin:0 auto; background:#ffffff; border:1px solid #d9e4f2; border-radius:22px; border-collapse:collapse; overflow:hidden;">
    <tr>
      <td align="center" style="padding:32px 32px 24px; background:#1a3a6e;">
        <!--[if gte mso 9]>
        <v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false" style="width:560px;">
        <v:fill type="gradient" color="#0f172a" color2="#2563eb" angle="135" />
        <v:textbox inset="0,0,0,0">
        <![endif]-->
        <div style="background:linear-gradient(135deg, #0f172a 0%, #2563eb 100%); padding:32px 32px 24px; text-align:center;">
          <img src="{_LOGO_URL}" alt="Pythinker" width="64" height="64" style="display:block; margin:0 auto; border:0; border-radius:16px; background:rgba(255,255,255,0.14); padding:8px;" />
          <p style="margin:16px 0 0; color:#dbeafe; font-size:13px; font-weight:600; letter-spacing:0.08em; text-transform:uppercase;">
            Pythinker
          </p>
        </div>
        <!--[if gte mso 9]>
        </v:textbox>
        </v:rect>
        <![endif]-->
      </td>
    </tr>
    <tr>
      <td style="padding:32px;">
        <p style="margin:0 0 12px; color:#2563eb; font-size:12px; font-weight:700; letter-spacing:0.12em; text-transform:uppercase;">
          {eyebrow}
        </p>
        <h1 style="margin:0 0 14px; color:#0f172a; font-size:30px; line-height:1.2;">
          {heading}
        </h1>
        <p style="margin:0; color:#475569; font-size:16px; line-height:1.7;">
          {intro}
        </p>
        <div style="margin:28px 0 20px; padding:24px; border-radius:20px; background:#f5f8ff; border:1px solid #c7d7fe; text-align:center;">
          <p style="margin:0 0 10px; color:#64748b; font-size:12px; font-weight:600; letter-spacing:0.08em; text-transform:uppercase;">
            Verification code
          </p>
          <p style="margin:0; color:#0f172a; font-size:34px; font-weight:700; letter-spacing:0.34em; font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;">
            {code}
          </p>
        </div>
        <div style="padding:18px 20px; border-radius:16px; background:#f8fafc; border:1px solid #e2e8f0;">
          <p style="margin:0; color:#475569; font-size:14px; line-height:1.7;">
            {detail}
          </p>
        </div>
        <p style="margin:20px 0 0; color:#64748b; font-size:13px; line-height:1.7;">
          {ignore_note}
        </p>
        <hr style="margin:28px 0 18px; border:none; border-top:1px solid #e2e8f0;" />
        <p style="margin:0; color:#94a3b8; font-size:12px; line-height:1.6; text-align:center;">
          Pythinker &bull; Secure account access
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


@dataclass(frozen=True)
class VerificationState:
    expires_at: datetime
    resend_available_at: datetime
    resends_remaining: int


@dataclass(frozen=True)
class VerificationResult:
    is_valid: bool
    error_code: str | None = None
    attempts_remaining: int | None = None


class EmailService:
    """Email service for sending verification codes and notifications"""

    VERIFICATION_CODE_PREFIX = "verification_code:"
    VERIFICATION_CODE_EXPIRY_SECONDS = 600  # 10 minutes
    VERIFICATION_MAX_ATTEMPTS = 5
    VERIFICATION_RESEND_COOLDOWN_SECONDS = 60
    VERIFICATION_MAX_RESENDS = 3

    def __init__(self, cache: Cache):
        self.settings = get_settings()
        self.cache = cache

    def _generate_verification_code(self) -> str:
        """Generate 6-digit verification code using cryptographically secure random."""
        return f"{secrets.randbelow(900000) + 100000}"

    def _verification_key(self, email: str, purpose: str) -> str:
        return f"{self.VERIFICATION_CODE_PREFIX}{purpose}:{email}"

    def _attempts_key(self, key: str) -> str:
        return f"{key}:attempts"

    def _build_verification_state(self, code_data: dict[str, object]) -> VerificationState:
        raw_count = code_data.get("resend_count", 0)
        resend_count = int(raw_count) if isinstance(raw_count, (int, float, str)) else 0
        return VerificationState(
            expires_at=datetime.fromisoformat(str(code_data["expires_at"])),
            resend_available_at=datetime.fromisoformat(str(code_data["resend_available_at"])),
            resends_remaining=max(self.VERIFICATION_MAX_RESENDS - resend_count, 0),
        )

    def build_placeholder_verification_state(self, *, now: datetime | None = None) -> VerificationState:
        reference = now or datetime.now(UTC)
        return VerificationState(
            expires_at=reference + timedelta(seconds=self.VERIFICATION_CODE_EXPIRY_SECONDS),
            resend_available_at=reference + timedelta(seconds=self.VERIFICATION_RESEND_COOLDOWN_SECONDS),
            resends_remaining=self.VERIFICATION_MAX_RESENDS,
        )

    def _build_code_data(self, code: str, now: datetime, resend_count: int) -> dict[str, object]:
        return {
            "code": code,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.VERIFICATION_CODE_EXPIRY_SECONDS)).isoformat(),
            "resend_available_at": (now + timedelta(seconds=self.VERIFICATION_RESEND_COOLDOWN_SECONDS)).isoformat(),
            "resend_count": resend_count,
            "attempts": 0,
        }

    async def _delete_verification_session(self, key: str) -> None:
        await self.cache.delete(key)
        await self.cache.delete(self._attempts_key(key))

    async def _get_active_code_data(self, key: str) -> tuple[dict[str, object] | None, VerificationState | None]:
        stored_data = await self.cache.get(key)
        if not isinstance(stored_data, dict):
            return None, None

        try:
            state = self._build_verification_state(stored_data)
        except (KeyError, TypeError, ValueError):
            await self._delete_verification_session(key)
            return None, None

        if datetime.now(UTC) >= state.expires_at:
            await self._delete_verification_session(key)
            return None, None

        return stored_data, state

    async def get_verification_state(self, email: str, purpose: str = "reset") -> VerificationState | None:
        key = self._verification_key(email, purpose)
        _, state = await self._get_active_code_data(key)
        return state

    async def _send_code(
        self,
        email: str,
        *,
        purpose: str,
        create_message: Callable[[str, str], Message],
    ) -> VerificationState:
        key = self._verification_key(email, purpose)
        existing_data, existing_state = await self._get_active_code_data(key)
        now = datetime.now(UTC)

        if existing_data and existing_state:
            if existing_state.resends_remaining == 0 or now < existing_state.resend_available_at:
                return existing_state
            raw = existing_data.get("resend_count", 0)
            resend_count = (int(raw) if isinstance(raw, (int, float, str)) else 0) + 1
        else:
            resend_count = 0

        self._check_email_config()

        code = self._generate_verification_code()
        code_data = self._build_code_data(code, now, resend_count)
        msg = create_message(email, code)
        await self._send_smtp_email(msg, email)
        await self.cache.delete(self._attempts_key(key))
        await self.cache.set(key, code_data, ttl=self.VERIFICATION_CODE_EXPIRY_SECONDS)
        return self._build_verification_state(code_data)

    async def verify_code(self, email: str, code: str, purpose: str = "reset") -> VerificationResult:
        """Verify a provided OTP code and return a structured result."""
        key = self._verification_key(email, purpose)
        stored_data, state = await self._get_active_code_data(key)
        if not stored_data or not state:
            return VerificationResult(is_valid=False, error_code="code_expired")

        now = datetime.now(UTC)
        remaining_ttl = max(int((state.expires_at - now).total_seconds()), 1)
        attempts_key = self._attempts_key(key)
        new_attempts = await self.cache.increment(attempts_key, ttl=remaining_ttl)

        if new_attempts is None:
            # NullCache fallback: increment() is not supported, so we use a
            # separate counter key to avoid stale-read issues on stored_data.
            # NOTE: NullCache is inherently single-process; this is safe only
            # in that context.  Multi-process deployments MUST use Redis.
            fallback_count = await self.cache.get(attempts_key)
            new_attempts = (int(fallback_count) if fallback_count is not None else 0) + 1
            await self.cache.set(attempts_key, new_attempts, ttl=remaining_ttl)

        if secrets.compare_digest(str(stored_data["code"]), code):
            await self._delete_verification_session(key)
            return VerificationResult(is_valid=True)

        attempts_remaining = max(self.VERIFICATION_MAX_ATTEMPTS - new_attempts, 0)
        if new_attempts >= self.VERIFICATION_MAX_ATTEMPTS:
            await self._delete_verification_session(key)
            return VerificationResult(
                is_valid=False,
                error_code="code_attempts_exhausted",
                attempts_remaining=0,
            )

        return VerificationResult(
            is_valid=False,
            error_code="code_invalid",
            attempts_remaining=attempts_remaining,
        )

    def _create_code_email(
        self,
        *,
        email: str,
        code: str,
        subject: str,
        eyebrow: str,
        heading: str,
        intro: str,
        detail: str,
        ignore_note: str,
    ) -> MIMEMultipart:
        from_addr = self.settings.email_from or self.settings.email_username
        plain = _build_code_email_text(
            heading=heading,
            intro=intro,
            code=code,
            detail=detail,
            ignore_note=ignore_note,
        )
        html = _build_code_email_html(
            eyebrow=eyebrow,
            heading=heading,
            intro=intro,
            code=code,
            detail=detail,
            ignore_note=ignore_note,
        )

        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        msg["From"] = f"Pythinker <{from_addr}>"
        msg["To"] = email
        msg["Subject"] = subject
        return msg

    def _create_verification_email(self, email: str, code: str) -> MIMEMultipart:
        """Create password-reset verification email with branded template."""
        return self._create_code_email(
            email=email,
            code=code,
            subject="Password Reset — Pythinker",
            eyebrow="Secure verification",
            heading="Reset your password",
            intro="Use this one-time verification code to continue resetting your Pythinker password.",
            detail="This code expires in 10 minutes. Only enter it in the password reset flow you started.",
            ignore_note="If you did not request a password reset, no changes have been made to your account.",
        )

    def _check_email_config(self) -> None:
        """Raise if email configuration is incomplete."""
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

    async def send_verification_code(self, email: str) -> VerificationState:
        """Send verification code for password reset."""
        state = await self._send_code(email, purpose="reset", create_message=self._create_verification_email)
        logger.info("Verification code available for %s", _mask_email(email))
        return state

    def _create_registration_verification_email(self, email: str, code: str) -> MIMEMultipart:
        """Create registration verification email with branded template."""
        return self._create_code_email(
            email=email,
            code=code,
            subject="Verify Your Email — Pythinker",
            eyebrow="Account setup",
            heading="Verify your email address",
            intro="Welcome to Pythinker. Enter this one-time code to finish setting up your account securely.",
            detail="This code expires in 10 minutes. For your security, only enter it on the Pythinker verification screen.",
            ignore_note="If you did not create a Pythinker account, you can ignore this email.",
        )

    async def send_registration_verification_code(self, email: str) -> VerificationState:
        """Send verification code for registration email verification."""
        state = await self._send_code(
            email,
            purpose="registration",
            create_message=self._create_registration_verification_email,
        )
        logger.info("Registration verification code available for %s", _mask_email(email))
        return state

    async def _send_smtp_email(self, msg: Message, email: str) -> None:
        """Send email using SMTP via thread pool to avoid blocking the event loop."""
        host = self.settings.email_host
        port = self.settings.email_port
        username = self.settings.email_username
        password = self.settings.email_password
        text = msg.as_string()
        # Extract bare email for SMTP envelope (MAIL FROM expects "user@domain", not "Name <user@domain>")
        _, from_addr = parseaddr(msg["From"])

        def _smtp_send() -> None:
            server = None
            try:
                logger.debug("Creating SMTP connection to %s:%s", host, port)
                if port == 465:
                    server = smtplib.SMTP_SSL(host, port, timeout=30)
                else:
                    server = smtplib.SMTP(host, port, timeout=30)
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                server.login(username, password)
                server.sendmail(from_addr, email, text)
                logger.debug("SMTP email sent to %s", _mask_email(email))
            finally:
                if server:
                    server.quit()

        await asyncio.to_thread(_smtp_send)

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

        from_addr = self.settings.email_from or self.settings.email_username
        msg = MIMEMultipart()
        msg["From"] = f"Pythinker <{from_addr}>"
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
        """Clean up expired verification codes - Cache TTL handles this automatically."""
        pattern = f"{self.VERIFICATION_CODE_PREFIX}*"
        keys = await self.cache.keys(pattern)

        expired_count = 0
        for key in keys:
            data = await self.cache.get(key)
            if not isinstance(data, dict):
                continue
            try:
                expires_at = datetime.fromisoformat(str(data["expires_at"]))
                if datetime.now(UTC) > expires_at:
                    await self._delete_verification_session(key)
                    expired_count += 1
            except (KeyError, ValueError):
                await self._delete_verification_session(key)
                expired_count += 1

        if expired_count > 0:
            logger.info("Cleaned up %s expired verification codes", expired_count)
