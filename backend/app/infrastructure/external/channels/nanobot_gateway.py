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
from typing import TYPE_CHECKING

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

from app.domain.models.channel import ChannelType, InboundMessage, OutboundMessage

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


class NanobotGateway:
    """Infrastructure adapter that bridges nanobot channels into Pythinker.

    Implements the ``ChannelGateway`` protocol defined in
    ``app.domain.external.channel_gateway``.
    """

    # Seconds without a successful channel poll before emitting a WARNING.
    POLL_WATCHDOG_TIMEOUT: float = 20.0
    # Grace window for long-running inbound routing before considering it a stall.
    INBOUND_PROCESSING_WARN_TIMEOUT: float = 180.0

    def __init__(
        self,
        message_router: MessageRouter,
        *,
        telegram_token: str = "",
        telegram_allowed: list[str] | None = None,
        telegram_rate_limit_cooldown_seconds: int = 3,
        telegram_max_messages_per_batch: int = 5,
        telegram_pdf_file_id_cache_redis_enabled: bool = False,
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

        # Build nanobot Config from Pythinker settings
        channels_cfg = ChannelsConfig(
            send_progress=send_progress,
            send_tool_hints=send_tool_hints,
            telegram=TelegramConfig(
                enabled=bool(telegram_token),
                token=telegram_token,
                allow_from=telegram_allowed or ["*"],
                rate_limit_cooldown_seconds=telegram_rate_limit_cooldown_seconds,
                max_messages_per_batch=telegram_max_messages_per_batch,
                pdf_file_id_cache_redis_enabled=telegram_pdf_file_id_cache_redis_enabled,
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

        nb_outbound = NbOutbound(
            channel=nb_channel,
            chat_id=message.chat_id,
            content=message.content,
            reply_to=message.reply_to,
            media=[m.url for m in message.media],
            metadata=message.metadata,
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
                    processing_started = self._inbound_processing_started_monotonic
                    if processing_started is not None:
                        processing_age = now - processing_started
                        if processing_age < self.INBOUND_PROCESSING_WARN_TIMEOUT:
                            logger.debug(
                                "NanobotGateway: no poll activity while processing inbound message (%.1fs, grace %.0fs)",
                                processing_age,
                                self.INBOUND_PROCESSING_WARN_TIMEOUT,
                            )
                            continue
                        logger.warning(
                            "NanobotGateway: inbound processing appears stalled for %.1fs without channel poll activity "
                            "(poll timeout %.0fs)",
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
                self._inbound_processing_started_monotonic = asyncio.get_running_loop().time()
                pt_msg = self._convert_inbound(nb_msg)
                logger.info(
                    "Inbound message from %s sender=%s chat=%s",
                    pt_msg.channel,
                    pt_msg.sender_id,
                    pt_msg.chat_id,
                )

                # Route and relay outbound replies
                try:
                    async for outbound in self._message_router.route_inbound(pt_msg):
                        await self.send_to_channel(outbound)
                except Exception:
                    logger.exception(
                        "Error routing inbound message from %s/%s",
                        nb_msg.channel,
                        nb_msg.chat_id,
                    )
                finally:
                    self._inbound_processing_started_monotonic = None
                    # Route completion counts as poll activity for watchdog health.
                    self._activity_event.set()
        except asyncio.CancelledError:
            logger.info("Inbound consumer cancelled")
            raise

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_inbound(nb_msg: NbInbound) -> InboundMessage:
        """Convert a nanobot ``InboundMessage`` to a Pythinker ``InboundMessage``."""
        channel_type = _CHANNEL_MAP.get(nb_msg.channel, ChannelType.WEB)
        return InboundMessage(
            channel=channel_type,
            sender_id=nb_msg.sender_id,
            chat_id=nb_msg.chat_id,
            content=nb_msg.content,
            timestamp=nb_msg.timestamp,
            metadata=nb_msg.metadata,
            session_key_override=nb_msg.session_key_override,
        )
