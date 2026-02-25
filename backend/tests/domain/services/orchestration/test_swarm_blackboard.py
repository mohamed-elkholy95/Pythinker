"""Smoke tests for WP fix: Swarm StateManifest blackboard now initialises without crash.

Prior bug: Swarm.__init__ called StateManifest() with no arguments, but session_id
is a required Pydantic field — this raised ValidationError on every Swarm instantiation.

Fix: session_id parameter added to Swarm.__init__; UUID generated when not provided.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.state_manifest import StateManifest
from app.domain.services.orchestration.swarm import Swarm, SwarmConfig


def _make_agent_factory() -> MagicMock:
    factory = MagicMock()
    factory.create_agent = AsyncMock(return_value=MagicMock())
    factory.execute_agent = AsyncMock(return_value=iter([]))
    return factory


def test_swarm_init_no_session_id_does_not_raise():
    """Swarm.__init__ must not raise ValidationError when session_id is omitted."""
    swarm = Swarm(agent_factory=_make_agent_factory())
    assert swarm._shared_state is not None
    assert isinstance(swarm._shared_state, StateManifest)
    # A UUID was auto-generated
    assert len(swarm._session_id) > 0


def test_swarm_init_with_explicit_session_id():
    """session_id is forwarded to the StateManifest when explicitly provided."""
    swarm = Swarm(
        agent_factory=_make_agent_factory(),
        session_id="my-session-42",
    )
    assert swarm._shared_state.session_id == "my-session-42"
    assert swarm._session_id == "my-session-42"


def test_swarm_init_generates_unique_ids_when_not_provided():
    """Each Swarm instance gets its own unique session_id when none is passed."""
    swarm_a = Swarm(agent_factory=_make_agent_factory())
    swarm_b = Swarm(agent_factory=_make_agent_factory())
    assert swarm_a._session_id != swarm_b._session_id


def test_swarm_shared_state_accepts_entries():
    """StateManifest on Swarm is functional — entries can be posted and retrieved."""
    from app.domain.models.state_manifest import StateEntry

    swarm = Swarm(agent_factory=_make_agent_factory(), session_id="s-test")
    swarm._shared_state.post(
        StateEntry(key="result", value={"answer": 42}, posted_by="agent-1")
    )
    entry = swarm._shared_state.get("result")
    assert entry is not None
    assert entry.value == {"answer": 42}


def test_swarm_config_passed_through():
    """SwarmConfig is honoured alongside the new session_id parameter."""
    config = SwarmConfig(max_concurrent_agents=2)
    swarm = Swarm(
        agent_factory=_make_agent_factory(),
        config=config,
        session_id="cfg-session",
    )
    assert swarm._config.max_concurrent_agents == 2
    assert swarm._shared_state.session_id == "cfg-session"
