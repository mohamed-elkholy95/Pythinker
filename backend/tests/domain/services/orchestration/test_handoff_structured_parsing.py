"""Smoke tests for Phase 2: Handoff structured JSON parsing.

Prior state: Handoff detection only used regex [HANDOFF]...[/HANDOFF] markers.

Fix: _detect_handoff_request() now tries JSON-first parsing:
  {"handoff": {"agent": "researcher", "task": "...", "expected_output": "..."}}
and falls back to regex markers for backward compatibility.
"""

from unittest.mock import MagicMock

from app.domain.services.orchestration.swarm import Swarm, SwarmTask


def _make_swarm(session_id: str = "test-s") -> Swarm:
    factory = MagicMock()
    return Swarm(agent_factory=factory, session_id=session_id)


def _make_task(description: str = "Test task") -> SwarmTask:
    from app.domain.services.orchestration.swarm import AgentType

    task = SwarmTask(description=description, original_request=description)
    task.assigned_agent = AgentType.COORDINATOR
    return task


def test_detect_handoff_json_first_researcher():
    """JSON-format handoff to 'researcher' is parsed via structured path."""
    swarm = _make_swarm()
    task = _make_task()

    message = '{"handoff": {"agent": "researcher", "task": "Find sources", "expected_output": "Citations list"}}'
    handoff = swarm._detect_handoff_request(message, task)

    assert handoff is not None, "JSON handoff should be detected"
    from app.domain.services.orchestration.agent_types import AgentType

    assert handoff.target_agent == AgentType.RESEARCHER


def test_detect_handoff_json_unknown_agent_returns_none():
    """JSON handoff with an unknown agent name returns None."""
    swarm = _make_swarm()
    task = _make_task()

    message = '{"handoff": {"agent": "unknownbot", "task": "Do something"}}'
    handoff = swarm._detect_handoff_request(message, task)
    assert handoff is None


def test_detect_handoff_regex_fallback():
    """Legacy [HANDOFF]...[/HANDOFF] marker still works as fallback."""
    swarm = _make_swarm()
    task = _make_task("Analyse data")

    message = "[HANDOFF]\nagent: analyst\ntask: Analyse the CSV\n[/HANDOFF]"
    handoff = swarm._detect_handoff_request(message, task)

    assert handoff is not None, "Regex-marker handoff should be detected via fallback"


def test_detect_handoff_no_marker_returns_none():
    """Plain message with no handoff signal returns None."""
    swarm = _make_swarm()
    task = _make_task()

    message = "The task is complete. No further delegation needed."
    handoff = swarm._detect_handoff_request(message, task)
    assert handoff is None


def test_detect_handoff_json_with_nested_handoff_key():
    """JSON payload with nested 'handoff' key is correctly extracted."""
    swarm = _make_swarm()
    task = _make_task()

    message = 'Partial text {"handoff": {"agent": "coder", "task": "Write the script"}} more text'
    handoff = swarm._detect_handoff_request(message, task)

    assert handoff is not None
    from app.domain.services.orchestration.agent_types import AgentType

    assert handoff.target_agent == AgentType.CODER


def test_detect_handoff_malformed_json_falls_back_to_regex():
    """Malformed JSON is silently skipped and regex path is tried."""
    swarm = _make_swarm()
    task = _make_task("Process files")

    # Malformed JSON + valid regex marker
    message = '{"handoff": {broken} [HANDOFF]\nagent: writer\ntask: Write report\n[/HANDOFF]'
    handoff = swarm._detect_handoff_request(message, task)

    # Regex fallback should still find the [HANDOFF] marker
    assert handoff is not None


def test_parse_structured_handoff_returns_none_for_empty_agent():
    """_parse_structured_handoff() returns None when agent field is empty."""
    swarm = _make_swarm()
    task = _make_task()

    handoff = swarm._parse_structured_handoff({"handoff": {"agent": "", "task": "Do something"}}, task)
    assert handoff is None
