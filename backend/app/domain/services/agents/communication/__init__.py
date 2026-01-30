"""
Agent Communication module for inter-agent messaging.

Provides structured communication protocols for agent collaboration.
"""

from app.domain.services.agents.communication.protocol import (
    CommunicationProtocol,
    get_communication_protocol,
    reset_communication_protocol,
)

__all__ = [
    "CommunicationProtocol",
    "get_communication_protocol",
    "reset_communication_protocol",
]
