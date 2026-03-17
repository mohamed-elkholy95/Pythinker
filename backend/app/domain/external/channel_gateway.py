"""Channel gateway protocol — domain-layer contract for multi-channel messaging.

Infrastructure adapters (Telegram, Discord, etc.) implement this protocol.
The domain layer depends only on this abstraction, never on concrete channels.

Follows the same Protocol pattern as domain/external/scraper.py.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.channel import ChannelType, OutboundMessage


@runtime_checkable
class ChannelGateway(Protocol):
    """Gateway for sending messages to external channels.

    Implementations manage the lifecycle of channel adapters and
    provide a unified interface for outbound message delivery.
    """

    async def start(self) -> None:
        """Start all configured channel adapters."""
        ...

    async def stop(self) -> None:
        """Gracefully stop all channel adapters."""
        ...

    async def send_to_channel(self, message: OutboundMessage) -> None:
        """Send a message to a specific channel.

        Args:
            message: The outbound message containing channel, recipient,
                     and text content.

        Raises:
            ChannelDeliveryError: If delivery fails after retries.
        """
        ...

    def get_active_channels(self) -> list[ChannelType]:
        """Return list of currently active channel types."""
        ...
