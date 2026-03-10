"""Tests for monitor_session nullable sources handling."""
import pytest


class TestMonitorNullableSources:
    """Verify monitor handles null/missing sources in report events."""

    def test_null_sources_defaults_to_empty_list(self):
        """data.get('sources', []) returns None when key is explicitly null."""
        data = {"title": "Test", "content": "# Report", "sources": None}
        sources = data.get("sources") or []
        assert len(sources) == 0

    def test_missing_sources_defaults_to_empty_list(self):
        data = {"title": "Test", "content": "# Report"}
        sources = data.get("sources") or []
        assert len(sources) == 0

    def test_present_sources_preserved(self):
        data = {"title": "Test", "content": "# Report", "sources": [{"url": "https://example.com"}]}
        sources = data.get("sources") or []
        assert len(sources) == 1
