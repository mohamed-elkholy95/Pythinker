"""Tests for the 3-layer channel session config overlay."""

from app.domain.models.channel_overlay import ChannelSessionOverlay, resolve_session_config


def _default() -> ChannelSessionOverlay:
    """Return a fully-populated default config used across tests."""
    return ChannelSessionOverlay(
        model_name="gpt-4o",
        thinking_enabled=False,
        subagent_enabled=True,
        max_delegates=3,
        tool_budget=20,
        clarification_enabled=True,
    )


def test_default_only() -> None:
    """Single-layer resolution preserves all default field values."""
    default = _default()
    result = resolve_session_config(default)

    assert result.model_name == "gpt-4o"
    assert result.thinking_enabled is False
    assert result.subagent_enabled is True
    assert result.max_delegates == 3
    assert result.tool_budget == 20
    assert result.clarification_enabled is True


def test_channel_overrides_default() -> None:
    """Channel layer overrides thinking_enabled; model_name is inherited from default."""
    channel = ChannelSessionOverlay(thinking_enabled=True)
    result = resolve_session_config(_default(), channel_config=channel)

    assert result.thinking_enabled is True  # overridden by channel
    assert result.model_name == "gpt-4o"  # inherited from default
    assert result.tool_budget == 20  # inherited from default


def test_user_overrides_channel() -> None:
    """User layer overrides model_name set by channel layer."""
    channel = ChannelSessionOverlay(model_name="claude-3-5-sonnet", tool_budget=10)
    user = ChannelSessionOverlay(model_name="o3-mini")
    result = resolve_session_config(_default(), channel_config=channel, user_config=user)

    assert result.model_name == "o3-mini"  # user wins over channel
    assert result.tool_budget == 10  # channel wins over default
    assert result.thinking_enabled is False  # inherited from default


def test_none_fields_dont_override() -> None:
    """Explicit None in a higher-priority layer does not override a concrete value below."""
    channel = ChannelSessionOverlay(
        model_name=None,  # should NOT override default's "gpt-4o"
        thinking_enabled=True,
    )
    result = resolve_session_config(_default(), channel_config=channel)

    assert result.model_name == "gpt-4o"  # None did not override
    assert result.thinking_enabled is True  # explicit True was applied
