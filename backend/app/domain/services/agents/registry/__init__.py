"""
Agent Registry module for capability tracking and routing.

Provides agent registration, capability discovery, and
intelligent routing based on task requirements.
"""

from app.domain.services.agents.registry.capability_registry import (
    AgentRegistry,
    get_agent_registry,
    reset_agent_registry,
)

__all__ = [
    "AgentRegistry",
    "get_agent_registry",
    "reset_agent_registry",
]
