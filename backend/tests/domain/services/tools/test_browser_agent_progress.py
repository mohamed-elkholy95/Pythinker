from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.services.tools import browser_agent as browser_agent_module
from app.domain.services.tools.browser_agent import BROWSER_USE_AVAILABLE, BrowserAgentTool

pytestmark = pytest.mark.skipif(not BROWSER_USE_AVAILABLE, reason="browser_use package is required")


class _FakeAction:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self, *, exclude_none: bool = True, mode: str = "json") -> dict[str, Any]:
        del exclude_none, mode
        return self._payload


class _FakeHistoryEntry:
    def __init__(self, *, action_payload: dict[str, Any], metadata: dict[str, Any] | None, url: str) -> None:
        self.model_output = SimpleNamespace(action=[_FakeAction(action_payload)])
        self.result = [SimpleNamespace(metadata=metadata)]
        self.state = SimpleNamespace(url=url)


class _FakeHistory:
    def __init__(self, entries: list[_FakeHistoryEntry]) -> None:
        self.history = entries

    def final_result(self) -> str:
        return "ok"

    def number_of_steps(self) -> int:
        return len(self.history)

    def is_successful(self) -> bool:
        return True

    def has_errors(self) -> bool:
        return False

    def urls(self) -> list[str]:
        return [entry.state.url for entry in self.history]


class _FakeAgent:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs
        self.history: _FakeHistory | None = None

    async def run(self, *, max_steps: int, on_step_end=None, on_step_start=None):  # type: ignore[no-untyped-def]
        del max_steps
        if self.history is None:
            raise AssertionError("test must set FakeAgent.history before run")
        if on_step_start is not None:
            await on_step_start(self)
        if on_step_end is not None:
            await on_step_end(self)
        return self.history


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        browser_agent_max_steps=8,
        browser_agent_timeout=10,
        browser_agent_use_vision=False,
        browser_agent_max_failures=1,
        browser_agent_llm_timeout=10,
        browser_agent_step_timeout=10,
        browser_agent_flash_mode=False,
    )


@pytest.mark.asyncio
async def test_browser_agent_progress_emits_click_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser_agent_run should enqueue progress with click metadata coordinates."""
    fake_agent = _FakeAgent()
    fake_agent.history = _FakeHistory(
        [
            _FakeHistoryEntry(
                action_payload={"click": {"index": 12}},
                metadata={"click_x": 480, "click_y": 320},
                url="https://example.com/login",
            )
        ]
    )
    monkeypatch.setattr(browser_agent_module, "Agent", lambda *args, **kwargs: fake_agent)

    tool = BrowserAgentTool("http://localhost:9222")
    tool._settings = _settings()
    tool._active_tool_call_id = "tool-call-1"
    tool._active_function_name = "browser_agent_run"

    async def _fake_get_browser() -> object:
        return object()

    monkeypatch.setattr(tool, "_get_browser", _fake_get_browser)
    monkeypatch.setattr(tool, "_get_llm", lambda: object())

    result = await tool._run_agent_task(task="Click login and continue", start_url="https://example.com/login")
    assert result["success"] is True

    events = [event async for event in tool.drain_progress_events()]
    assert len(events) == 1

    event = events[0]
    assert event.tool_call_id == "tool-call-1"
    assert event.function_name == "browser_agent_run"
    assert "click" in event.current_step.lower()
    assert event.checkpoint_data is not None
    assert event.checkpoint_data["action"] == "click"
    assert event.checkpoint_data["action_function"] == "browser_click"
    assert event.checkpoint_data["coordinate_x"] == 480
    assert event.checkpoint_data["coordinate_y"] == 320


@pytest.mark.asyncio
async def test_browser_agent_progress_emits_navigation_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser_agent_run should enqueue progress for navigation actions."""
    fake_agent = _FakeAgent()
    fake_agent.history = _FakeHistory(
        [
            _FakeHistoryEntry(
                action_payload={"navigate": {"url": "https://example.com/docs"}},
                metadata=None,
                url="https://example.com/docs",
            )
        ]
    )
    monkeypatch.setattr(browser_agent_module, "Agent", lambda *args, **kwargs: fake_agent)

    tool = BrowserAgentTool("http://localhost:9222")
    tool._settings = _settings()
    tool._active_tool_call_id = "tool-call-2"
    tool._active_function_name = "browser_agent_run"

    async def _fake_get_browser() -> object:
        return object()

    monkeypatch.setattr(tool, "_get_browser", _fake_get_browser)
    monkeypatch.setattr(tool, "_get_llm", lambda: object())

    result = await tool._run_agent_task(task="Open docs", start_url="https://example.com/docs")
    assert result["success"] is True

    events = [event async for event in tool.drain_progress_events()]
    assert len(events) == 1

    event = events[0]
    assert event.checkpoint_data is not None
    assert event.checkpoint_data["action"] == "navigate"
    assert event.checkpoint_data["action_function"] == "browser_navigate"
    assert event.checkpoint_data["url"] == "https://example.com/docs"
