"""Tests for provider profile controls — configurable max_results and search_depth."""

from app.infrastructure.external.search.brave_search import BraveSearchEngine
from app.infrastructure.external.search.exa_search import ExaSearchEngine
from app.infrastructure.external.search.serper_search import SerperSearchEngine
from app.infrastructure.external.search.tavily_search import TavilySearchEngine


def _make_tavily(max_results: int = 8, search_depth: str = "basic") -> TavilySearchEngine:
    return TavilySearchEngine(api_key="test-key", max_results=max_results, search_depth=search_depth)


def _make_serper(max_results: int = 8) -> SerperSearchEngine:
    return SerperSearchEngine(api_key="test-key", max_results=max_results)


def _make_brave(max_results: int = 8) -> BraveSearchEngine:
    return BraveSearchEngine(api_key="test-key", max_results=max_results)


def _make_exa(max_results: int = 8, search_type: str = "auto") -> ExaSearchEngine:
    return ExaSearchEngine(api_key="test-key", max_results=max_results, search_type=search_type)


class TestTavilyProfile:
    def test_default_max_results_is_8(self):
        engine = _make_tavily()
        params = engine._build_request_params("test", None)
        assert params["max_results"] == 8

    def test_custom_max_results(self):
        engine = _make_tavily(max_results=15)
        params = engine._build_request_params("test", None)
        assert params["max_results"] == 15

    def test_default_search_depth_is_basic(self):
        engine = _make_tavily()
        params = engine._build_request_params("test", None)
        assert params["search_depth"] == "basic"

    def test_custom_search_depth_advanced(self):
        engine = _make_tavily(search_depth="advanced")
        params = engine._build_request_params("test", None)
        assert params["search_depth"] == "advanced"

    def test_max_results_5_returns_5(self):
        engine = _make_tavily(max_results=5)
        params = engine._build_request_params("test query", None)
        assert params["max_results"] == 5


class TestSerperProfile:
    def test_default_num_is_8(self):
        engine = _make_serper()
        params = engine._build_request_params("test", None)
        assert params["num"] == 8

    def test_custom_num(self):
        engine = _make_serper(max_results=12)
        params = engine._build_request_params("test", None)
        assert params["num"] == 12


class TestBraveProfile:
    def test_default_count_is_8(self):
        engine = _make_brave()
        params = engine._build_request_params("test", None)
        assert params["count"] == 8

    def test_custom_count(self):
        engine = _make_brave(max_results=10)
        params = engine._build_request_params("test", None)
        assert params["count"] == 10


class TestExaProfile:
    def test_default_num_results_is_8(self):
        engine = _make_exa()
        params = engine._build_request_params("test", None)
        assert params["numResults"] == 8

    def test_custom_num_results(self):
        engine = _make_exa(max_results=20)
        params = engine._build_request_params("test", None)
        assert params["numResults"] == 20

    def test_default_type_is_auto(self):
        engine = _make_exa()
        params = engine._build_request_params("test", None)
        assert params["type"] == "auto"

    def test_custom_type_neural(self):
        engine = _make_exa(search_type="neural")
        params = engine._build_request_params("test", None)
        assert params["type"] == "neural"
