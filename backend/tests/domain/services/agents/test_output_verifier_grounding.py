"""Tests for grounding context — ensure LLM-generated content doesn't self-validate."""
import pytest
from unittest.mock import MagicMock
from app.domain.services.agents.output_verifier import OutputVerifier


class TestGroundingContextIntegrity:
    """Verify grounding context excludes LLM-generated key_facts when external sources exist."""

    def _make_verifier(self, sources: list, key_facts: list[str] | None = None) -> OutputVerifier:
        """Create OutputVerifier with mock dependencies."""
        source_tracker = MagicMock()
        source_tracker._collected_sources = sources
        context_manager = MagicMock()
        if key_facts is not None:
            context_manager._context.key_facts = key_facts
        else:
            context_manager._context.key_facts = []
        return OutputVerifier(
            llm=MagicMock(),
            critic=None,
            cove=None,
            context_manager=context_manager,
            source_tracker=source_tracker,
        )

    def _make_source(self, title: str, url: str, snippet: str, source_type: str = "search") -> MagicMock:
        src = MagicMock()
        src.title = title
        src.url = url
        src.snippet = snippet
        src.source_type = source_type
        return src

    def test_external_sources_present_excludes_key_facts(self):
        """When external search/browser sources exist, key_facts should NOT be included."""
        sources = [
            self._make_source("GitHub Trending", "https://github.com/trending", "Python repos trending today", "search"),
        ]
        key_facts = [
            "OpenManus has 55K stars on GitHub",
            "anthropics/skills is the most popular repo",
        ]
        verifier = self._make_verifier(sources, key_facts)
        chunks = verifier.build_source_context()
        combined = " ".join(chunks)
        assert "55K stars" not in combined
        assert "most popular repo" not in combined
        assert "GitHub Trending" in combined

    def test_no_external_sources_allows_key_facts(self):
        """When no external sources exist, key_facts are the only grounding — include them."""
        sources = []
        key_facts = ["The project uses Python 3.12 and has comprehensive test coverage"]
        verifier = self._make_verifier(sources, key_facts)
        chunks = verifier.build_source_context()
        combined = " ".join(chunks)
        assert "Python 3.12" in combined

    def test_empty_sources_with_no_key_facts_returns_empty(self):
        """When neither sources nor key_facts exist, return empty list."""
        verifier = self._make_verifier([], [])
        chunks = verifier.build_source_context()
        assert chunks == []
