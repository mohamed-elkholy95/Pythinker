import logging

from app.domain.models.search import SearchResultItem
from app.infrastructure.external.search.base import SearchEngineBase, SearchEngineType


class DummySearchEngine(SearchEngineBase):
    provider_name = "dummy"
    engine_type = SearchEngineType.API

    def _get_date_range_mapping(self) -> dict[str, str]:
        return {}

    def _build_request_params(self, query: str, date_range: str | None) -> dict[str, str]:
        return {"q": query}

    async def _execute_request(self, client, params):
        raise NotImplementedError

    def _parse_response(self, response):
        return [], 0


def test_filter_english_results_removes_chinese_items():
    engine = DummySearchEngine()
    results = [
        SearchResultItem(title="Python async patterns", link="https://example.com/a", snippet="Guide"),
        SearchResultItem(title="中文教程", link="https://example.com/b", snippet="Python 入门"),
    ]

    filtered = engine._filter_english_results(results)

    assert len(filtered) == 1
    assert filtered[0].title == "Python async patterns"


def test_filter_english_results_keeps_non_chinese_items():
    engine = DummySearchEngine()
    results = [
        SearchResultItem(title="Guide to LangChain", link="https://example.com/a", snippet="Practical tips"),
        SearchResultItem(title="Tutoriel Python", link="https://example.com/b", snippet="Pour debutants"),
    ]

    filtered = engine._filter_english_results(results)

    assert len(filtered) == 2


def test_create_error_result_logs_expected_exhaustion_as_warning(caplog):
    engine = DummySearchEngine()

    caplog.set_level(logging.WARNING)
    result = engine._create_error_result("gpu deals", None, "All 6 Serper API keys exhausted")

    assert result.success is False
    warning_messages = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert any("All 6 Serper API keys exhausted" in message for message in warning_messages)
    assert not any(record.levelname == "ERROR" for record in caplog.records)


def test_create_error_result_logs_unexpected_failure_as_error(caplog):
    engine = DummySearchEngine()

    caplog.set_level(logging.ERROR)
    result = engine._create_error_result("gpu deals", None, "Unexpected parser failure")

    assert result.success is False
    error_messages = [record.getMessage() for record in caplog.records if record.levelname == "ERROR"]
    assert any("Unexpected parser failure" in message for message in error_messages)
