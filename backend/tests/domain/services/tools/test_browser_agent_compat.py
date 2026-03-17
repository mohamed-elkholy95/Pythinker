"""Tests for SanitizedChatOpenAI compat_mode — browser-use LLM provider compatibility."""

from __future__ import annotations

import pytest

# browser_use is an optional dependency; skip tests if not installed
browser_use = pytest.importorskip("browser_use", reason="browser_use not installed")

from app.domain.services.tools.browser_agent import SanitizedChatOpenAI  # noqa: E402


class TestSanitizedChatOpenAICompatMode:
    """Verify that compat_mode correctly configures browser-use flags."""

    def _make_llm(self, *, compat_mode: bool) -> SanitizedChatOpenAI:
        """Create a SanitizedChatOpenAI with minimal required params."""
        return SanitizedChatOpenAI(
            model="test-model",
            api_key="test-key",
            base_url="https://example.com/v1",
            temperature=0.0,
            compat_mode=compat_mode,
        )

    # ── compat_mode=True (non-OpenAI providers) ──────────────────────────

    def test_compat_mode_disables_structured_output(self) -> None:
        llm = self._make_llm(compat_mode=True)
        assert llm.dont_force_structured_output is True

    def test_compat_mode_enables_schema_in_system_prompt(self) -> None:
        llm = self._make_llm(compat_mode=True)
        assert llm.add_schema_to_system_prompt is True

    def test_compat_mode_nullifies_frequency_penalty(self) -> None:
        llm = self._make_llm(compat_mode=True)
        assert llm.frequency_penalty is None

    def test_compat_mode_nullifies_max_completion_tokens(self) -> None:
        llm = self._make_llm(compat_mode=True)
        assert llm.max_completion_tokens is None

    # ── compat_mode=False (native OpenAI) ─────────────────────────────────

    def test_default_mode_keeps_structured_output(self) -> None:
        llm = self._make_llm(compat_mode=False)
        assert llm.dont_force_structured_output is False

    def test_default_mode_does_not_inject_schema_prompt(self) -> None:
        llm = self._make_llm(compat_mode=False)
        assert llm.add_schema_to_system_prompt is False

    def test_default_mode_keeps_frequency_penalty(self) -> None:
        llm = self._make_llm(compat_mode=False)
        # browser-use default is 0.3, but we pass temperature=0.0 so
        # frequency_penalty keeps its ChatOpenAI default
        assert llm.frequency_penalty is not None

    def test_default_mode_keeps_max_completion_tokens(self) -> None:
        llm = self._make_llm(compat_mode=False)
        assert llm.max_completion_tokens is not None

    # ── compat_mode default ───────────────────────────────────────────────

    def test_compat_mode_defaults_to_false(self) -> None:
        llm = SanitizedChatOpenAI(
            model="test-model",
            api_key="test-key",
        )
        assert llm.compat_mode is False
        assert llm.dont_force_structured_output is False
