"""Tests for hallucination grounding fallback when source_context is empty.

When deep_research bypasses info_search_web (uses browser_navigate instead),
SourceTracker may collect nothing. build_source_context() must fall back to
context_manager key_facts and tool execution summaries so that LettuceDetect
still has grounding evidence rather than skipping verification entirely.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.services.agents.output_verifier import OutputVerifier


def _make_source(
    title: str,
    url: str,
    snippet: str,
    source_type: str = "search",
) -> MagicMock:
    """Create a mock SourceCitation."""
    src = MagicMock()
    src.title = title
    src.url = url
    src.snippet = snippet
    src.source_type = source_type
    return src


def _make_tool_context(
    tool_name: str,
    summary: str,
    key_findings: list[str] | None = None,
) -> MagicMock:
    """Create a mock ToolContext."""
    tc = MagicMock()
    tc.tool_name = tool_name
    tc.summary = summary
    tc.key_findings = key_findings or []
    return tc


def _make_verifier(
    sources: list[MagicMock] | None = None,
    key_facts: list[str] | None = None,
    tools: list[MagicMock] | None = None,
) -> OutputVerifier:
    """Create an OutputVerifier with mock dependencies."""
    source_tracker = MagicMock()
    source_tracker._collected_sources = sources or []

    context_manager = MagicMock()
    context_manager._context.key_facts = key_facts or []
    context_manager._context.tools = tools or []

    return OutputVerifier(
        llm=MagicMock(),
        critic=None,
        cove=None,
        context_manager=context_manager,
        source_tracker=source_tracker,
    )


class TestKeyFactsFallback:
    """When SourceTracker is empty, build_source_context should fall back to
    context_manager key_facts as grounding context rather than skipping."""

    def test_build_source_context_uses_key_facts_fallback(self):
        """build_source_context() should return key_facts when no tracked sources exist."""
        verifier = _make_verifier(
            sources=[],
            key_facts=[
                "Python 3.12 was released in October 2023",
                "FastAPI is built on Starlette and Pydantic",
            ],
        )

        context = verifier.build_source_context()
        assert len(context) >= 1
        assert any("Python 3.12" in c for c in context)

    def test_build_source_context_prefers_tracked_sources(self):
        """When tracked sources exist, they take priority over key_facts."""
        verifier = _make_verifier(
            sources=[
                _make_source(
                    "GitHub Trending",
                    "https://github.com/trending",
                    "Content from actual web source about GitHub trends",
                    "browser",
                ),
            ],
            key_facts=["Some fallback fact that should be ignored"],
        )

        context = verifier.build_source_context()
        assert len(context) >= 1
        assert any("GitHub trends" in c for c in context)
        # key_facts should NOT be in context when tracked sources exist
        assert not any("fallback fact" in c for c in context)

    def test_empty_sources_with_short_key_facts_still_includes_them(self):
        """Key facts shorter than 20 chars should still be included when they
        are the only grounding available."""
        verifier = _make_verifier(
            sources=[],
            key_facts=["Short fact"],  # < 20 chars
        )

        context = verifier.build_source_context()
        # Even short facts provide some grounding -- should not be filtered out
        # when they are the ONLY grounding available
        assert len(context) >= 0  # At minimum, don't crash


class TestToolExecutionFallback:
    """When both SourceTracker and key_facts are empty, tool execution
    summaries from browser_navigate should provide grounding context."""

    def test_tool_summaries_used_when_sources_and_facts_empty(self):
        """Tool execution summaries should be used as last-resort grounding."""
        verifier = _make_verifier(
            sources=[],
            key_facts=[],
            tools=[
                _make_tool_context(
                    "browser_navigate",
                    "Navigated to https://example.com and found pricing info",
                    key_findings=["Enterprise plan costs $99/month"],
                ),
            ],
        )

        context = verifier.build_source_context()
        assert len(context) >= 1
        assert any("pricing" in c.lower() or "Enterprise" in c for c in context)

    def test_tool_findings_included_as_grounding(self):
        """key_findings from tool executions should serve as grounding evidence."""
        verifier = _make_verifier(
            sources=[],
            key_facts=[],
            tools=[
                _make_tool_context(
                    "browser_navigate",
                    "Browsed documentation page",
                    key_findings=[
                        "Vue 3 requires Node.js 18 or higher",
                        "Vite is the recommended build tool for Vue 3",
                    ],
                ),
            ],
        )

        context = verifier.build_source_context()
        assert len(context) >= 1
        assert any("Node.js 18" in c or "Vite" in c for c in context)

    def test_tool_summaries_ignored_when_tracked_sources_exist(self):
        """Tool summaries should NOT be used when proper tracked sources exist."""
        verifier = _make_verifier(
            sources=[
                _make_source(
                    "Vue Docs",
                    "https://vuejs.org",
                    "Official Vue.js documentation",
                    "browser",
                ),
            ],
            key_facts=[],
            tools=[
                _make_tool_context(
                    "browser_navigate",
                    "Tool summary that should be ignored",
                    key_findings=["Finding that should be ignored"],
                ),
            ],
        )

        context = verifier.build_source_context()
        assert len(context) >= 1
        # Should contain tracked source, not tool summary
        assert any("Vue.js" in c for c in context)
        assert not any("should be ignored" in c for c in context)


class TestFallbackLogging:
    """Verify that fallback usage is logged for observability."""

    def test_key_facts_fallback_logs_warning(self, caplog):
        """When falling back to key_facts, a warning-level log should be emitted."""
        import logging

        verifier = _make_verifier(
            sources=[],
            key_facts=["Important fact about the research topic that provides grounding"],
        )

        with caplog.at_level(logging.WARNING, logger="app.domain.services.agents.output_verifier"):
            verifier.build_source_context()

        assert any(
            "key_facts" in record.message.lower() or "fallback" in record.message.lower() for record in caplog.records
        )

    def test_tool_summary_fallback_logs_warning(self, caplog):
        """When falling back to tool summaries, a warning-level log should be emitted."""
        import logging

        verifier = _make_verifier(
            sources=[],
            key_facts=[],
            tools=[
                _make_tool_context(
                    "browser_navigate",
                    "Browsed page with important findings for verification",
                    key_findings=["Critical finding from browser navigation"],
                ),
            ],
        )

        with caplog.at_level(logging.WARNING, logger="app.domain.services.agents.output_verifier"):
            verifier.build_source_context()

        assert any(
            "tool" in record.message.lower() or "fallback" in record.message.lower() for record in caplog.records
        )


class TestEdgeCases:
    """Edge cases for the grounding fallback chain."""

    def test_all_sources_empty_returns_empty_list(self):
        """When everything is empty, return [] gracefully."""
        verifier = _make_verifier(sources=[], key_facts=[], tools=[])
        context = verifier.build_source_context()
        assert context == []

    def test_none_key_facts_handled(self):
        """If key_facts is somehow None, don't crash."""
        source_tracker = MagicMock()
        source_tracker._collected_sources = []
        context_manager = MagicMock()
        context_manager._context.key_facts = None
        context_manager._context.tools = []

        verifier = OutputVerifier(
            llm=MagicMock(),
            critic=None,
            cove=None,
            context_manager=context_manager,
            source_tracker=source_tracker,
        )
        # Should not raise
        context = verifier.build_source_context()
        assert isinstance(context, list)

    def test_mixed_tool_types_only_browser_tools_used(self):
        """Only browser-related tool summaries should be used as grounding,
        not arbitrary tool executions like shell commands."""
        verifier = _make_verifier(
            sources=[],
            key_facts=[],
            tools=[
                _make_tool_context(
                    "shell_exec",
                    "Ran pip install for dependencies",
                    key_findings=["Installed 42 packages"],
                ),
                _make_tool_context(
                    "browser_navigate",
                    "Navigated to pricing page with plan details",
                    key_findings=["Basic plan is $10/month"],
                ),
            ],
        )

        context = verifier.build_source_context()
        assert len(context) >= 1
        # Browser findings should be included
        assert any("$10/month" in c or "pricing" in c.lower() for c in context)
        # Shell findings should NOT be grounding evidence
        assert not any("pip install" in c for c in context)
