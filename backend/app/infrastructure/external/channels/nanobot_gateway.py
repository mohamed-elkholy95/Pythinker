"""NanobotGateway — wraps nanobot's ChannelManager + MessageBus to implement
Pythinker's ChannelGateway protocol.

Nanobot code runs unmodified.  This adapter:
1. Builds a nanobot ``Config`` from Pythinker settings.
2. Creates a ``MessageBus`` and ``ChannelManager``.
3. Consumes inbound messages from the bus and forwards them to ``MessageRouter``.
4. Publishes outbound ``OutboundMessage`` objects to the bus for delivery.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from nanobot.bus.events import InboundMessage as NbInbound
from nanobot.bus.events import OutboundMessage as NbOutbound
from nanobot.bus.queue import MessageBus
from nanobot.channels.manager import ChannelManager
from nanobot.config.schema import (
    ChannelsConfig,
    Config,
    DiscordConfig,
    EmailConfig,
    SlackConfig,
    TelegramConfig,
    WhatsAppConfig,
)

from app.domain.models.channel import ChannelType, InboundMessage, MediaAttachment, OutboundMessage

if TYPE_CHECKING:
    from app.domain.services.channels.message_router import MessageRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Nanobot channel name → Pythinker ChannelType mapping
# ---------------------------------------------------------------------------
_CHANNEL_MAP: dict[str, ChannelType] = {
    "telegram": ChannelType.TELEGRAM,
    "discord": ChannelType.DISCORD,
    "slack": ChannelType.SLACK,
    "whatsapp": ChannelType.WHATSAPP,
    "email": ChannelType.EMAIL,
}

# Reverse lookup for outbound
_CHANNEL_REVERSE: dict[ChannelType, str] = {v: k for k, v in _CHANNEL_MAP.items()}


@dataclass(slots=True)
class _QueuedInboundMessage:
    """Inbound message wrapper with enqueue timestamp for latency telemetry."""

    message: NbInbound
    received_monotonic: float


class NanobotGateway:
    """Infrastructure adapter that bridges nanobot channels into Pythinker.

    Implements the ``ChannelGateway`` protocol defined in
    ``app.domain.external.channel_gateway``.
    """

    # Seconds without a successful channel poll before emitting a WARNING.
    POLL_WATCHDOG_TIMEOUT: float = 20.0
    # Grace window for long-running inbound routing before considering it a stall.
    INBOUND_PROCESSING_WARN_TIMEOUT: float = 180.0
    # How long an idle per-chat worker can stay alive before self-terminating.
    INBOUND_CHAT_WORKER_IDLE_SECONDS: float = 30.0

    def __init__(
        self,
        message_router: MessageRouter,
        *,
        telegram_token: str = "",
        telegram_allowed: list[str] | None = None,
        telegram_webhook_mode: bool = False,
        telegram_webhook_url: str = "",
        telegram_webhook_secret: str = "",
        telegram_webhook_path: str = "/telegram-webhook",
        telegram_webhook_host: str = "127.0.0.1",
        telegram_webhook_port: int = 8787,
        telegram_proxy_url: str = "",
        telegram_reaction_notifications: str = "own",
        telegram_dm_policy: str = "open",
        telegram_group_policy: str = "open",
        telegram_group_require_mention: bool = False,
        telegram_group_allowed: list[str] | None = None,
        telegram_groups: dict[str, dict[str, object]] | None = None,
        telegram_direct: dict[str, dict[str, object]] | None = None,
        telegram_reply_to_mode: str = "off",
        telegram_rate_limit_cooldown_seconds: int = 3,
        telegram_max_messages_per_batch: int = 5,
        telegram_inline_buttons_scope: Literal["off", "dm", "group", "all", "allowlist"] = "allowlist",
        telegram_pdf_file_id_cache_redis_enabled: bool = False,
        telegram_final_delivery_only: bool = True,
        telegram_final_delivery_allow_wait_prompts: bool = True,
        telegram_streaming: str = "partial",
        telegram_streaming_throttle_seconds: float = 1.0,
        telegram_streaming_min_initial_chars: int = 30,
        telegram_polling_bootstrap_retries: int = 5,
        telegram_polling_stall_restart_enabled: bool = True,
        telegram_polling_stall_timeout_seconds: float = 60.0,
        telegram_send_retry_max_attempts: int = 5,
        telegram_send_retry_base_delay_seconds: float = 1.0,
        telegram_send_retry_max_delay_seconds: float = 30.0,
        telegram_send_retry_jitter: bool = True,
        telegram_send_circuit_breaker_enabled: bool = True,
        telegram_send_circuit_failure_threshold: int = 5,
        telegram_send_circuit_recovery_timeout_seconds: int = 30,
        discord_token: str = "",
        discord_allowed: list[str] | None = None,
        slack_bot_token: str = "",
        slack_app_token: str = "",
        slack_allowed: list[str] | None = None,
        whatsapp_bridge_url: str = "ws://localhost:3001",
        whatsapp_allowed: list[str] | None = None,
        email_imap_host: str = "",
        email_imap_port: int = 993,
        email_imap_username: str = "",
        email_imap_password: str = "",
        email_smtp_host: str = "",
        email_smtp_port: int = 587,
        email_smtp_username: str = "",
        email_smtp_password: str = "",
        email_from_address: str = "",
        email_allowed: list[str] | None = None,
        send_progress: bool = True,
        send_tool_hints: bool = False,
    ) -> None:
        self._message_router = message_router
        self._consumer_task: asyncio.Task[None] | None = None
        self._channels_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        # Signalled by _consume_inbound on each successful bus poll iteration.
        self._activity_event: asyncio.Event = asyncio.Event()
        # Monotonic timestamp when current inbound message routing started.
        self._inbound_processing_started_monotonic: float | None = None
        # Monotonic timestamp for most recent observed progress while routing an inbound message.
        self._inbound_processing_last_progress_monotonic: float | None = None
        # Per-chat workers allow concurrent processing across independent chats while preserving
        # message ordering within each chat/session key.
        self._inbound_worker_queues: dict[str, asyncio.Queue[_QueuedInboundMessage]] = {}
        self._inbound_worker_tasks: dict[str, asyncio.Task[None]] = {}
        self._inbound_processing_started_by_key: dict[str, float] = {}
        self._inbound_processing_last_progress_by_key: dict[str, float] = {}

        # Build nanobot Config from Pythinker settings
        channels_cfg = ChannelsConfig(
            send_progress=send_progress,
            send_tool_hints=send_tool_hints,
            telegram=TelegramConfig(
                enabled=bool(telegram_token),
                token=telegram_token,
                allow_from=telegram_allowed or ["*"],
                webhook_mode=telegram_webhook_mode,
                webhook_url=telegram_webhook_url,
                webhook_secret=telegram_webhook_secret,
                webhook_path=telegram_webhook_path,
                webhook_host=telegram_webhook_host,
                webhook_port=telegram_webhook_port,
                proxy=telegram_proxy_url or None,
                reaction_notifications=telegram_reaction_notifications,
                dm_policy=telegram_dm_policy,
                group_policy=telegram_group_policy,
                group_require_mention=telegram_group_require_mention,
                group_allow_from=telegram_group_allowed or [],
                groups=telegram_groups or {},
                direct=telegram_direct or {},
                reply_to_mode=telegram_reply_to_mode,
                rate_limit_cooldown_seconds=telegram_rate_limit_cooldown_seconds,
                max_messages_per_batch=telegram_max_messages_per_batch,
                inline_buttons_scope=telegram_inline_buttons_scope,
                pdf_file_id_cache_redis_enabled=telegram_pdf_file_id_cache_redis_enabled,
                final_delivery_only=telegram_final_delivery_only,
                final_delivery_allow_wait_prompts=telegram_final_delivery_allow_wait_prompts,
                streaming=telegram_streaming,
                streaming_throttle_seconds=telegram_streaming_throttle_seconds,
                streaming_min_initial_chars=telegram_streaming_min_initial_chars,
                polling_bootstrap_retries=telegram_polling_bootstrap_retries,
                polling_stall_restart_enabled=telegram_polling_stall_restart_enabled,
                polling_stall_timeout_seconds=telegram_polling_stall_timeout_seconds,
                send_retry_max_attempts=telegram_send_retry_max_attempts,
                send_retry_base_delay_seconds=telegram_send_retry_base_delay_seconds,
                send_retry_max_delay_seconds=telegram_send_retry_max_delay_seconds,
                send_retry_jitter=telegram_send_retry_jitter,
                send_circuit_breaker_enabled=telegram_send_circuit_breaker_enabled,
                send_circuit_failure_threshold=telegram_send_circuit_failure_threshold,
                send_circuit_recovery_timeout_seconds=telegram_send_circuit_recovery_timeout_seconds,
            ),
            discord=DiscordConfig(
                enabled=bool(discord_token),
                token=discord_token,
                allow_from=discord_allowed or ["*"],
            ),
            slack=SlackConfig(
                enabled=bool(slack_bot_token),
                bot_token=slack_bot_token,
                app_token=slack_app_token,
                allow_from=slack_allowed or ["*"],
            ),
            whatsapp=WhatsAppConfig(
                enabled=bool(whatsapp_bridge_url and whatsapp_allowed),
                bridge_url=whatsapp_bridge_url,
                allow_from=whatsapp_allowed or [],
            ),
            email=EmailConfig(
                enabled=bool(email_imap_host and email_smtp_host),
                imap_host=email_imap_host,
                imap_port=email_imap_port,
                imap_username=email_imap_username,
                imap_password=email_imap_password,
                smtp_host=email_smtp_host,
                smtp_port=email_smtp_port,
                smtp_username=email_smtp_username,
                smtp_password=email_smtp_password,
                from_address=email_from_address,
                allow_from=email_allowed or ["*"],
            ),
        )

        nb_config = Config(channels=channels_cfg)

        self._bus = MessageBus()
        self._channel_manager = ChannelManager(nb_config, self._bus)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the nanobot ChannelManager and the inbound consumer loop."""
        logger.info(
            "NanobotGateway starting — enabled channels: %s",
            self._channel_manager.enabled_channels,
        )
        # Start channels in background (start_all blocks until channels stop)
        self._channels_task = asyncio.create_task(self._channel_manager.start_all())
        # Start inbound consumer
        self._consumer_task = asyncio.create_task(self._consume_inbound())
        # Start polling watchdog
        self._activity_event.set()  # Pre-signal so watchdog doesn't fire immediately
        self._watchdog_task = asyncio.create_task(self._run_poll_watchdog())

    async def stop(self) -> None:
        """Stop the consumer loop and all nanobot channels."""
        logger.info("NanobotGateway stopping...")

        # Cancel watchdog first (prevents spurious warnings during shutdown)
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
            self._watchdog_task = None

        # Cancel consumer first
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
            self._consumer_task = None

        # Cancel per-chat inbound workers
        await self._cancel_inbound_workers()

        # Stop all channels
        await self._channel_manager.stop_all()
        logger.info("NanobotGateway stopped")

    # ------------------------------------------------------------------
    # Outbound (Pythinker → nanobot bus → channel)
    # ------------------------------------------------------------------

    async def send_to_channel(self, message: OutboundMessage) -> None:
        """Convert a Pythinker OutboundMessage to a nanobot OutboundMessage and publish."""
        nb_channel = _CHANNEL_REVERSE.get(message.channel)
        if nb_channel is None:
            logger.warning(
                "Cannot send to channel %s — not mapped to nanobot",
                message.channel,
            )
            return

        metadata = dict(message.metadata)
        if message.media:
            metadata["media_attachments"] = [
                {
                    "url": media.url,
                    "content_type": media.mime_type,
                    "filename": media.filename,
                    "size": media.size_bytes,
                    "metadata": media.metadata,
                }
                for media in message.media
            ]

        nb_outbound = NbOutbound(
            channel=nb_channel,
            chat_id=message.chat_id,
            content=message.content,
            reply_to=message.reply_to,
            media=[m.url for m in message.media],
            metadata=metadata,
        )
        await self._bus.publish_outbound(nb_outbound)

    # ------------------------------------------------------------------
    # Active channels query
    # ------------------------------------------------------------------

    def get_active_channels(self) -> list[ChannelType]:
        """Return Pythinker ChannelType list for all enabled nanobot channels."""
        result: list[ChannelType] = []
        for nb_name in self._channel_manager.enabled_channels:
            pt_type = _CHANNEL_MAP.get(nb_name)
            if pt_type is not None:
                result.append(pt_type)
        return result

    # ------------------------------------------------------------------
    # Inbound consumer (nanobot bus → MessageRouter)
    # ------------------------------------------------------------------

    async def _run_poll_watchdog(self) -> None:
        """Watchdog: log a WARNING when the inbound consumer stalls for > POLL_WATCHDOG_TIMEOUT s.

        Detects event-loop blocks, nanobot channel hangs, or network stalls that
        prevent the consumer from completing a poll cycle.  The _activity_event is
        set by _consume_inbound on every successful bus.consume_inbound() attempt.
        """
        try:
            while True:
                self._activity_event.clear()
                try:
                    await asyncio.wait_for(
                        self._activity_event.wait(),
                        timeout=self.POLL_WATCHDOG_TIMEOUT,
                    )
                except TimeoutError:
                    now = asyncio.get_running_loop().time()
                    processing_started, progress_idle_age, processing_age = self._get_processing_watchdog_stats(now)
                    if processing_started is not None:
                        if progress_idle_age < self.INBOUND_PROCESSING_WARN_TIMEOUT:
                            logger.debug(
                                "NanobotGateway: no poll activity while processing inbound message "
                                "(idle %.1fs, total %.1fs, grace %.0fs)",
                                progress_idle_age,
                                processing_age,
                                self.INBOUND_PROCESSING_WARN_TIMEOUT,
                            )
                            continue
                        logger.warning(
                            "NanobotGateway: inbound processing appears stalled for %.1fs since last progress "
                            "(total %.1fs, poll timeout %.0fs)",
                            progress_idle_age,
                            processing_age,
                            self.POLL_WATCHDOG_TIMEOUT,
                        )
                        continue

                    logger.warning(
                        "NanobotGateway: no channel poll activity for %.0fs — "
                        "possible event-loop block or Telegram/Discord connection stall",
                        self.POLL_WATCHDOG_TIMEOUT,
                    )
        except asyncio.CancelledError:
            pass

    async def _consume_inbound(self) -> None:
        """Loop: consume inbound messages from the nanobot bus, convert
        to Pythinker ``InboundMessage``, route through ``MessageRouter``,
        and publish any outbound replies back to the bus.
        """
        logger.info("Inbound consumer started")
        try:
            while True:
                try:
                    nb_msg: NbInbound = await asyncio.wait_for(
                        self._bus.consume_inbound(),
                        timeout=1.0,
                    )
                except TimeoutError:
                    self._activity_event.set()  # Idle poll still counts as activity
                    continue

                self._activity_event.set()  # Signal successful message receipt to watchdog
                await self._enqueue_inbound_message(nb_msg)
        except asyncio.CancelledError:
            logger.info("Inbound consumer cancelled")
            raise

    async def _enqueue_inbound_message(self, nb_msg: NbInbound) -> None:
        """Enqueue inbound message to a per-chat worker queue."""
        route_key = self._inbound_route_key(nb_msg)
        queue = self._inbound_worker_queues.get(route_key)
        if queue is None:
            queue = asyncio.Queue()
            self._inbound_worker_queues[route_key] = queue

        queued_message = _QueuedInboundMessage(
            message=nb_msg,
            received_monotonic=asyncio.get_running_loop().time(),
        )
        await queue.put(queued_message)

        worker_task = self._inbound_worker_tasks.get(route_key)
        if worker_task is None or worker_task.done():
            self._inbound_worker_tasks[route_key] = asyncio.create_task(
                self._run_inbound_worker(route_key),
                name=f"nanobot-inbound-worker:{route_key}",
            )

    async def _run_inbound_worker(self, route_key: str) -> None:
        """Process queued inbound messages sequentially for a specific chat key."""
        queue = self._inbound_worker_queues.get(route_key)
        if queue is None:
            return

        try:
            while True:
                try:
                    queued = await asyncio.wait_for(
                        queue.get(),
                        timeout=self.INBOUND_CHAT_WORKER_IDLE_SECONDS,
                    )
                except TimeoutError:
                    if queue.empty():
                        break
                    continue

                try:
                    await self._route_queued_inbound(route_key, queued)
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            raise
        finally:
            # Remove worker registration only if this task is still current.
            current = self._inbound_worker_tasks.get(route_key)
            if current is asyncio.current_task():
                self._inbound_worker_tasks.pop(route_key, None)

            queue_ref = self._inbound_worker_queues.get(route_key)
            if queue_ref is queue and queue.empty():
                self._inbound_worker_queues.pop(route_key, None)

            self._mark_inbound_processing_complete(route_key)
            self._activity_event.set()

    async def _route_queued_inbound(self, route_key: str, queued: _QueuedInboundMessage) -> None:
        """Route one queued inbound message through MessageRouter and channel delivery."""
        now = asyncio.get_running_loop().time()
        queued_ms = (now - queued.received_monotonic) * 1000.0
        self._mark_inbound_processing_started(route_key, now)

        pt_msg = self._convert_inbound(queued.message)
        logger.info(
            "Inbound message from %s sender=%s chat=%s",
            pt_msg.channel,
            pt_msg.sender_id,
            pt_msg.chat_id,
        )

        route_started_monotonic = asyncio.get_running_loop().time()
        first_outbound_ms: float | None = None
        outbound_count = 0

        try:
            async for outbound in self._message_router.route_inbound(pt_msg):
                outbound_count += 1
                send_started = asyncio.get_running_loop().time()
                if first_outbound_ms is None:
                    first_outbound_ms = (send_started - route_started_monotonic) * 1000.0
                self._mark_inbound_processing_progress(route_key, send_started)

                # Progress heartbeats update the stall tracker but don't send to user
                if outbound.metadata and outbound.metadata.get("_progress_heartbeat"):
                    self._activity_event.set()
                    continue

                await self.send_to_channel(outbound)
                self._mark_inbound_processing_progress(route_key, asyncio.get_running_loop().time())
                self._activity_event.set()
        except Exception:
            logger.exception(
                "Error routing inbound message from %s/%s",
                queued.message.channel,
                queued.message.chat_id,
            )
        finally:
            route_completed_monotonic = asyncio.get_running_loop().time()
            route_ms = (route_completed_monotonic - route_started_monotonic) * 1000.0
            first_outbound_field = "none" if first_outbound_ms is None else f"{first_outbound_ms:.2f}"
            queue_depth = (
                self._inbound_worker_queues.get(route_key).qsize() if route_key in self._inbound_worker_queues else 0
            )
            logger.info(
                "inbound_route_telemetry key=%s channel=%s chat=%s queued_ms=%.2f route_ms=%.2f "
                "first_outbound_ms=%s outbounds=%d queue_depth=%d",
                route_key,
                pt_msg.channel.value,
                pt_msg.chat_id,
                queued_ms,
                route_ms,
                first_outbound_field,
                outbound_count,
                queue_depth,
            )
            self._mark_inbound_processing_complete(route_key)
            self._activity_event.set()

    def _inbound_route_key(self, nb_msg: NbInbound) -> str:
        """Return routing key used for per-chat worker partitioning."""
        return nb_msg.session_key

    async def _cancel_inbound_workers(self) -> None:
        """Cancel all active per-chat inbound workers."""
        worker_tasks = list(self._inbound_worker_tasks.values())
        for task in worker_tasks:
            task.cancel()
        for task in worker_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self._inbound_worker_tasks.clear()
        self._inbound_worker_queues.clear()
        self._inbound_processing_started_by_key.clear()
        self._inbound_processing_last_progress_by_key.clear()
        self._inbound_processing_started_monotonic = None
        self._inbound_processing_last_progress_monotonic = None

    def _mark_inbound_processing_started(self, route_key: str, timestamp: float) -> None:
        self._inbound_processing_started_by_key[route_key] = timestamp
        self._inbound_processing_last_progress_by_key[route_key] = timestamp
        self._sync_legacy_processing_markers()

    def _mark_inbound_processing_progress(self, route_key: str, timestamp: float) -> None:
        if route_key in self._inbound_processing_started_by_key:
            self._inbound_processing_last_progress_by_key[route_key] = timestamp
            self._sync_legacy_processing_markers()

    def _mark_inbound_processing_complete(self, route_key: str) -> None:
        self._inbound_processing_started_by_key.pop(route_key, None)
        self._inbound_processing_last_progress_by_key.pop(route_key, None)
        self._sync_legacy_processing_markers()

    def _sync_legacy_processing_markers(self) -> None:
        """Keep legacy single-value fields in sync for existing diagnostics/tests."""
        if not self._inbound_processing_started_by_key:
            self._inbound_processing_started_monotonic = None
            self._inbound_processing_last_progress_monotonic = None
            return

        self._inbound_processing_started_monotonic = min(self._inbound_processing_started_by_key.values())
        self._inbound_processing_last_progress_monotonic = max(self._inbound_processing_last_progress_by_key.values())

    def _get_processing_watchdog_stats(self, now: float) -> tuple[float | None, float, float]:
        """Return processing presence + worst observed idle/age for watchdog logic."""
        if self._inbound_processing_started_by_key:
            oldest_started = min(self._inbound_processing_started_by_key.values())
            max_processing_age = max(now - started for started in self._inbound_processing_started_by_key.values())
            max_progress_idle_age = max(
                now - self._inbound_processing_last_progress_by_key.get(key, started)
                for key, started in self._inbound_processing_started_by_key.items()
            )
            return oldest_started, max_progress_idle_age, max_processing_age

        processing_started = self._inbound_processing_started_monotonic
        if processing_started is None:
            return None, 0.0, 0.0

        last_progress = self._inbound_processing_last_progress_monotonic or processing_started
        return processing_started, now - last_progress, now - processing_started

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_inbound(nb_msg: NbInbound) -> InboundMessage:
        """Convert a nanobot ``InboundMessage`` to a Pythinker ``InboundMessage``."""
        channel_type = _CHANNEL_MAP.get(nb_msg.channel, ChannelType.WEB)
        attachments: list[MediaAttachment] = []
        raw_media_attachments = nb_msg.metadata.get("media_attachments", [])
        if isinstance(raw_media_attachments, list):
            for item in raw_media_attachments:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "") or "").strip()
                if not url:
                    continue
                size_bytes = item.get("size", 0)
                attachments.append(
                    MediaAttachment(
                        url=url,
                        mime_type=str(item.get("content_type", "") or ""),
                        filename=str(item.get("filename", "") or ""),
                        size_bytes=size_bytes if isinstance(size_bytes, int) else 0,
                        metadata={
                            **({"type": item["type"]} if "type" in item else {}),
                            **(item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}),
                        },
                    )
                )

        if not attachments:
            raw_media_items = nb_msg.metadata.get("media_items", [])
            if isinstance(raw_media_items, list):
                for item in raw_media_items:
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url", "") or "").strip()
                    if not url:
                        continue
                    size_bytes = item.get("size_bytes", 0)
                    attachments.append(
                        MediaAttachment(
                            url=url,
                            mime_type=str(item.get("mime_type", "") or ""),
                            filename=str(item.get("filename", "") or ""),
                            size_bytes=size_bytes if isinstance(size_bytes, int) else 0,
                        )
                    )

        if not attachments:
            attachments = [MediaAttachment(url=str(url)) for url in nb_msg.media if str(url).strip()]

        return InboundMessage(
            channel=channel_type,
            sender_id=nb_msg.sender_id,
            chat_id=nb_msg.chat_id,
            content=nb_msg.content,
            timestamp=nb_msg.timestamp,
            media=attachments,
            metadata=nb_msg.metadata,
            session_key_override=nb_msg.session_key_override,
        )
