"""Custom Telegram webhook listener for channel-owned transport parity."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from aiohttp import web
from telegram import Update

_DEFAULT_BODY_TIMEOUT_SECONDS = 30.0
_DEFAULT_MAX_BODY_BYTES = 1024 * 1024


class _PayloadTooLargeError(Exception):
    """Raised when the inbound webhook body exceeds the configured limit."""


@dataclass(slots=True)
class TelegramWebhookListener:
    """Own a small aiohttp listener and enqueue Telegram updates into PTB."""

    application: object
    secret_token: str
    path: str = "/telegram-webhook"
    host: str = "127.0.0.1"
    port: int = 8787
    public_url: str | None = None
    allowed_updates: list[str] | tuple[str, ...] = field(default_factory=list)
    health_path: str = "/healthz"
    body_timeout_seconds: float = _DEFAULT_BODY_TIMEOUT_SECONDS
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES
    _runner: web.AppRunner | None = field(init=False, default=None, repr=False)
    _site: web.TCPSite | None = field(init=False, default=None, repr=False)
    _bound_port: int | None = field(init=False, default=None, repr=False)
    _stopped: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        self.secret_token = str(self.secret_token or "").strip()
        self.path = self._normalize_path(self.path, default="/telegram-webhook")
        self.health_path = self._normalize_path(self.health_path, default="/healthz")
        self.public_url = str(self.public_url or "").strip() or None
        self.allowed_updates = list(self.allowed_updates)

    @staticmethod
    def _normalize_path(value: str, *, default: str) -> str:
        normalized = str(value or "").strip() or default
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized

    @property
    def bound_port(self) -> int:
        if self._bound_port is None:
            raise RuntimeError("Webhook listener has not started yet")
        return self._bound_port

    @property
    def webhook_url(self) -> str:
        if self.public_url:
            return self.public_url
        host = "localhost" if self.host in {"0.0.0.0", "::"} else self.host  # noqa: S104
        return f"http://{host}:{self.bound_port}{self.path}"

    @property
    def health_url(self) -> str:
        host = "localhost" if self.host in {"0.0.0.0", "::"} else self.host  # noqa: S104
        return f"http://{host}:{self.bound_port}{self.health_path}"

    async def start(self) -> None:
        """Start listening locally and register the Telegram webhook."""
        if not self.secret_token:
            raise ValueError("Telegram webhook mode requires a non-empty webhook_secret")

        app = web.Application()
        app.router.add_get(self.health_path, self._handle_health)
        app.router.add_post(self.path, self._handle_update)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._bound_port = self._resolve_bound_port()

        try:
            await self.application.bot.set_webhook(
                url=self.webhook_url,
                secret_token=self.secret_token,
                allowed_updates=self.allowed_updates,
            )
        except Exception:
            await self._cleanup_runner()
            raise

    async def stop(self) -> None:
        """Stop the local listener and unregister Telegram's webhook."""
        if self._stopped:
            return
        self._stopped = True

        try:
            await self.application.bot.delete_webhook(drop_pending_updates=False)
        finally:
            await self._cleanup_runner()

    async def _cleanup_runner(self) -> None:
        if self._runner is None:
            return
        try:
            await self._runner.cleanup()
        finally:
            self._runner = None
            self._site = None

    def _resolve_bound_port(self) -> int:
        if self._site is None or self._site._server is None:  # type: ignore[attr-defined]
            raise RuntimeError("Webhook listener did not bind a TCP server")
        sockets = list(self._site._server.sockets or ())  # type: ignore[attr-defined]
        if not sockets:
            raise RuntimeError("Webhook listener did not expose any sockets")
        return int(sockets[0].getsockname()[1])

    async def _handle_health(self, request: web.Request) -> web.Response:
        del request
        return web.Response(text="ok")

    async def _handle_update(self, request: web.Request) -> web.Response:
        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret_header != self.secret_token:
            return web.Response(status=401, text="unauthorized")

        try:
            payload = await asyncio.wait_for(self._read_payload(request), timeout=self.body_timeout_seconds)
        except TimeoutError:
            return web.Response(status=408, text="Request body timeout")
        except _PayloadTooLargeError:
            return web.Response(status=413, text="Payload too large")
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        update = Update.de_json(payload, self.application.bot)
        await self.application.update_queue.put(update)
        return web.Response(status=200)

    async def _read_payload(self, request: web.Request) -> dict[str, object]:
        if request.content_length is not None and request.content_length > self.max_body_bytes:
            raise _PayloadTooLargeError

        chunks: list[bytes] = []
        total_bytes = 0
        async for chunk in request.content.iter_chunked(65536):
            total_bytes += len(chunk)
            if total_bytes > self.max_body_bytes:
                raise _PayloadTooLargeError
            chunks.append(chunk)

        raw = b"".join(chunks)
        body_text = raw.decode("utf-8") if raw else "{}"
        payload = json.loads(body_text)
        if not isinstance(payload, dict):
            raise json.JSONDecodeError("Telegram webhook payload must be an object", body_text, 0)
        return payload


async def start_telegram_webhook_listener(**kwargs) -> TelegramWebhookListener:
    """Helper to create and start a Telegram webhook listener."""
    listener = TelegramWebhookListener(**kwargs)
    await listener.start()
    return listener
