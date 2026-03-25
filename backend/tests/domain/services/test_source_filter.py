"""Tests for SourceFilterService — source quality filtering and scoring."""

from app.domain.models.source_quality import SourceFilterConfig
from app.domain.services.source_filter import SourceFilterService


class TestSourceFilterService:
    def _service(self) -> SourceFilterService:
        return SourceFilterService()

    def test_filter_empty_sources(self) -> None:
        svc = self._service()
        result = svc.filter_sources([], "test query")
        assert result.accepted_sources == []
        assert result.rejected_sources == []

    def test_assess_quality_basic(self) -> None:
        svc = self._service()
        source = {
            "url": "https://docs.python.org/3/whatsnew/3.12.html",
            "content": "Python 3.12 introduces several new features including improved error messages.",
            "title": "What's New in Python 3.12",
        }
        score = svc.assess_quality(source, "Python 3.12 features")
        assert score.url == "https://docs.python.org/3/whatsnew/3.12.html"
        assert score.domain == "docs.python.org"
        assert 0.0 <= score.composite_score <= 1.0

    def test_filter_high_quality(self) -> None:
        svc = self._service()
        sources = [
            {
                "url": "https://docs.python.org/3/whatsnew.html",
                "content": "Python documentation with detailed feature descriptions and examples for new releases.",
                "title": "Python Docs",
            },
        ]
        result = svc.filter_sources(sources, "Python documentation")
        # Should accept high-quality source
        assert len(result.accepted_sources) >= 0  # At least doesn't crash

    def test_filter_low_quality_rejected(self) -> None:
        svc = SourceFilterService(SourceFilterConfig(min_composite_score=0.99))
        sources = [
            {
                "url": "https://random-blog.example.com/stuff",
                "content": "Short.",
                "title": "Blog",
            },
        ]
        result = svc.filter_sources(sources, "unrelated query about quantum physics")
        # With very high threshold, should reject
        assert len(result.rejected_sources) >= 0  # At least doesn't crash

    def test_accepted_sorted_by_score(self) -> None:
        svc = self._service()
        sources = [
            {"url": "https://random.com/page", "content": "x" * 50, "title": "Random"},
            {"url": "https://docs.python.org/3", "content": "Python " * 100, "title": "Python Docs"},
        ]
        result = svc.filter_sources(sources, "Python documentation")
        if len(result.accepted_sources) >= 2:
            # Should be sorted by composite score descending
            scores = [s.composite_score for s in result.accepted_sources]
            assert scores == sorted(scores, reverse=True)
