"""Tests for complexity-aware wide research query limits.

Default: 3 queries. When complexity >= 0.8: up to 5 queries.
Complexity flows via SearchTool(complexity_score=...) constructor param.
"""

from unittest.mock import MagicMock


class TestComplexitySettings:
    """Config settings for query limits."""

    def test_default_limit_is_3(self):
        from app.core.config_features import SearchSettingsMixin

        assert SearchSettingsMixin.max_wide_research_queries == 3

    def test_complex_limit_default_is_5(self):
        from app.core.config_features import SearchSettingsMixin

        assert SearchSettingsMixin.max_wide_research_queries_complex == 5


class TestSearchToolComplexityParam:
    """SearchTool accepts and uses complexity_score parameter."""

    def test_search_tool_accepts_complexity_score(self):
        """Constructor should accept complexity_score without error."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=0.95)
        assert tool._complexity_score == 0.95

    def test_search_tool_defaults_complexity_to_none(self):
        """Without complexity_score, it defaults to None."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine)
        assert tool._complexity_score is None


class TestEffectiveQueryLimit:
    """wide_research should use higher limit for complex tasks."""

    def test_effective_max_is_5_when_complexity_high(self):
        """complexity_score >= 0.8 -> effective max = max_wide_research_queries_complex."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=1.0)
        assert tool._effective_max_wide_queries >= 5

    def test_effective_max_is_5_at_threshold(self):
        """complexity_score == 0.8 -> effective max = max_wide_research_queries_complex."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=0.8)
        assert tool._effective_max_wide_queries >= 5

    def test_effective_max_is_3_when_complexity_low(self):
        """complexity_score < 0.8 -> effective max = max_wide_research_queries (3)."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=0.5)
        assert tool._effective_max_wide_queries == 3

    def test_effective_max_is_3_when_no_complexity(self):
        """No complexity_score -> default limit."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine)
        assert tool._effective_max_wide_queries == 3

    def test_effective_max_is_3_when_complexity_below_threshold(self):
        """complexity_score = 0.79 -> still uses default limit."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=0.79)
        assert tool._effective_max_wide_queries == 3


class TestSetComplexityScore:
    """set_complexity_score() updates effective limit dynamically."""

    def test_set_complexity_upgrades_limit(self):
        """Setting high complexity after construction upgrades the limit."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine)
        assert tool._effective_max_wide_queries == 3

        tool.set_complexity_score(0.9)
        assert tool._complexity_score == 0.9
        assert tool._effective_max_wide_queries >= 5

    def test_set_complexity_downgrades_limit(self):
        """Setting low complexity after construction downgrades the limit."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=0.95)
        assert tool._effective_max_wide_queries >= 5

        tool.set_complexity_score(0.3)
        assert tool._effective_max_wide_queries == 3

    def test_set_complexity_to_none_uses_default(self):
        """Setting complexity to None reverts to default limit."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        tool = SearchTool(mock_engine, complexity_score=0.95)

        tool.set_complexity_score(None)
        assert tool._complexity_score is None
        assert tool._effective_max_wide_queries == 3
