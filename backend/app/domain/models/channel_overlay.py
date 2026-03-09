"""Channel session configuration overlay model.

Provides a 3-layer config resolution model for nanobot channels:
  1. default_config  — system-wide baseline (all fields set)
  2. channel_config  — per-channel overrides (None = inherit)
  3. user_config     — per-user overrides (None = inherit)

Each layer's non-None values override the accumulated result from lower layers.
"""

from __future__ import annotations

from pydantic import BaseModel


class ChannelSessionOverlay(BaseModel):
    """Session configuration overlay for a nanobot channel.

    All fields are optional; None means "inherit from the layer below".
    A fully-resolved overlay (produced by ``resolve_session_config``) will
    have every field populated with a concrete value.

    Attributes:
        model_name: LLM model identifier to use for this session.
        thinking_enabled: Whether extended thinking / chain-of-thought is on.
        subagent_enabled: Whether the agent may spawn sub-agents.
        max_delegates: Maximum number of sub-agent delegations allowed.
        tool_budget: Maximum tool calls permitted per session turn.
        clarification_enabled: Whether the agent may ask clarifying questions.
    """

    model_name: str | None = None
    thinking_enabled: bool | None = None
    subagent_enabled: bool | None = None
    max_delegates: int | None = None
    tool_budget: int | None = None
    clarification_enabled: bool | None = None


def resolve_session_config(
    default_config: ChannelSessionOverlay,
    channel_config: ChannelSessionOverlay | None = None,
    user_config: ChannelSessionOverlay | None = None,
) -> ChannelSessionOverlay:
    """Merge three configuration layers into a single resolved overlay.

    Resolution order (lowest → highest priority):
      1. ``default_config`` — must supply a concrete value for every field.
      2. ``channel_config`` — non-None fields override the default.
      3. ``user_config``    — non-None fields override the channel result.

    None values in a higher-priority layer do **not** override a concrete
    value from a lower-priority layer.

    Args:
        default_config: Base configuration layer; all fields should be set.
        channel_config: Optional per-channel overrides.
        user_config: Optional per-user overrides.

    Returns:
        A new ``ChannelSessionOverlay`` instance with all layers merged.
    """
    resolved: dict[str, object] = default_config.model_dump()

    for layer in (channel_config, user_config):
        if layer is None:
            continue
        resolved = {
            **resolved,
            **{k: v for k, v in layer.model_dump().items() if v is not None},
        }

    return ChannelSessionOverlay.model_validate(resolved)
