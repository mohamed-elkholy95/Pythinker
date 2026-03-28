"""Tests for per-step source accumulation in OutputVerifier."""

from urllib.parse import urlparse

from app.domain.services.agents.output_verifier import OutputVerifier


class TestStepSourceAccumulation:
    def _make_verifier(self):
        """Create a minimal OutputVerifier for testing step sources."""
        # Use __new__ to avoid full __init__ dependencies
        v = object.__new__(OutputVerifier)
        v._step_sources = []
        return v

    def test_add_step_source(self):
        v = self._make_verifier()
        v.add_step_source(
            title="MacBook M5 Review",
            url="https://example.com/review",
            snippet="M5 Pro scored 15,200 in Geekbench multi-core",
        )
        assert len(v._step_sources) == 1
        assert "M5 Pro scored 15,200" in v._step_sources[0]
        source_line = v._step_sources[0].splitlines()[0]
        parsed = urlparse(source_line[source_line.index("(") + 1 : -1])
        assert parsed.netloc == "example.com"

    def test_add_step_source_ignores_empty(self):
        v = self._make_verifier()
        v.add_step_source(title="Empty", url="", snippet="")
        v.add_step_source(title="Blank", url="", snippet="   ")
        assert len(v._step_sources) == 0

    def test_add_step_source_truncates_long_snippets(self):
        v = self._make_verifier()
        long_snippet = "x" * 1000
        v.add_step_source(title="Long", url="http://x.com", snippet=long_snippet)
        assert len(v._step_sources) == 1
        assert len(v._step_sources[0]) < 600  # 500 char snippet + title/url overhead

    def test_clear_step_sources(self):
        v = self._make_verifier()
        v.add_step_source(title="A", url="http://a.com", snippet="content a")
        v.add_step_source(title="B", url="http://b.com", snippet="content b")
        assert len(v._step_sources) == 2

        v.clear_step_sources()
        assert len(v._step_sources) == 0

    def test_multiple_sources_accumulate(self):
        v = self._make_verifier()
        for i in range(5):
            v.add_step_source(title=f"Source {i}", url=f"http://{i}.com", snippet=f"data {i}")
        assert len(v._step_sources) == 5
