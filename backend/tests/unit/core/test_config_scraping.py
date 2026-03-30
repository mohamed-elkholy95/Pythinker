"""Tests for scraping settings mixin."""

import pytest

from app.core.config_features import SearchSettingsMixin
from app.core.config_scraping import ScrapingSettingsMixin


@pytest.mark.unit
class TestScrapingSettingsMixin:
    """Tests for ScrapingSettingsMixin defaults."""

    def test_feature_flags_defaults(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_enhanced_fetch is True
        assert mixin.scraping_tool_enabled is False
        assert mixin.scraping_spider_enabled is False

    def test_escalation_defaults(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_escalation_enabled is True
        assert mixin.scraping_stealth_enabled is True

    def test_http_fetcher_defaults(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_default_impersonate == "chrome"
        assert mixin.scraping_http_timeout == 15
        assert mixin.scraping_http1_fallback_enabled is True
        assert mixin.scraping_headless is True

    def test_proxy_defaults(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_proxy_enabled is False
        assert mixin.scraping_proxy_list == ""
        assert mixin.scraping_proxy_strategy == "cyclic"

    def test_cache_defaults(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_cache_enabled is True
        assert mixin.scraping_cache_l1_max_size == 100
        assert mixin.scraping_cache_l2_ttl == 300
        assert mixin.scraping_cache_key_include_mode is True

    def test_batch_defaults(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_batch_max_concurrency == 3

    def test_adaptive_tracking_defaults(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_adaptive_tracking is False
        assert mixin.scraping_adaptive_storage_dir == "/tmp/scrapling_adaptive"

    def test_auto_enrich_defaults(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.search_auto_enrich_enabled is True
        assert mixin.search_auto_enrich_top_k == 5
        assert mixin.search_auto_enrich_snippet_chars == 2000
        assert mixin.search_auto_enrich_skip_dynamic_fallback is True

    def test_dynamic_timeout_default(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_dynamic_timeout == 15.0

    def test_content_thresholds(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_min_content_length == 500
        assert mixin.scraping_max_content_length == 100000

    def test_spider_top_k_default(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_spider_top_k == 5

    def test_hf_token_default_empty(self) -> None:
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_hf_token == ""

    def test_spider_deep_top_k_lower_than_standard(self) -> None:
        """Deep-research spider top-k must be lower to reduce memory pressure."""
        mixin = ScrapingSettingsMixin()
        assert mixin.scraping_spider_top_k_deep < mixin.scraping_spider_top_k


@pytest.mark.unit
class TestDeepResearchSearchBudgets:
    """Deep-research mode uses strictly higher compaction limits and enrichment budgets.

    These tests prove that the mode-aware knobs in SearchSettingsMixin are larger
    than the standard-mode defaults in ScrapingSettingsMixin, so deep-research
    flows get more aggressive enrichment while standard flows remain unchanged.
    """

    def test_enrich_top_k_deep_larger_than_standard(self) -> None:
        scraping = ScrapingSettingsMixin()
        search = SearchSettingsMixin()
        assert search.search_auto_enrich_top_k_deep > scraping.search_auto_enrich_top_k

    def test_enrich_snippet_chars_deep_larger_than_standard(self) -> None:
        scraping = ScrapingSettingsMixin()
        search = SearchSettingsMixin()
        assert search.search_auto_enrich_snippet_chars_deep > scraping.search_auto_enrich_snippet_chars

    def test_preview_count_deep_larger_than_standard(self) -> None:
        """Background preview count is higher in deep-research mode."""
        search = SearchSettingsMixin()
        assert search.search_preview_count_deep > 5  # standard default in CompactionProfile

    def test_compaction_max_results_deep_larger_than_standard(self) -> None:
        """Wide-research result cap is higher in deep mode."""
        search = SearchSettingsMixin()
        assert search.search_compaction_max_results_deep > 10  # standard CompactionProfile.max_results

    def test_deep_knobs_are_strictly_positive(self) -> None:
        search = SearchSettingsMixin()
        assert search.search_auto_enrich_top_k_deep > 0
        assert search.search_auto_enrich_snippet_chars_deep > 0
        assert search.search_preview_count_deep > 0
        assert search.search_compaction_max_results_deep > 0
        assert search.search_compaction_max_summaries_deep > 0
        assert search.search_compaction_summary_snippet_chars_deep > 0
