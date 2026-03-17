"""Tests for search quota management configuration settings."""

import pytest


class TestQuotaManagementSettings:
    """Verify all new quota/routing settings exist with correct defaults."""

    def test_quota_limits_exist(self, settings):
        assert settings.search_quota_tavily == 1000
        assert settings.search_quota_serper == 2500
        assert settings.search_quota_brave == 2000
        assert settings.search_quota_exa == 1000
        assert settings.search_quota_jina == 500

    def test_credit_optimization_defaults(self, settings):
        assert settings.search_default_depth == "basic"
        assert settings.search_upgrade_depth_threshold == 0.7
        assert settings.search_quality_early_stop == 5
        assert settings.search_prefer_free_scrapers_for_quick is True

    def test_enhanced_dedup_defaults(self, settings):
        assert settings.search_enhanced_dedup_enabled is True
        assert settings.search_dedup_jaccard_threshold == 0.6

    def test_budget_degrade_thresholds(self, settings):
        assert settings.search_budget_degrade_deep_threshold == 0.2
        assert settings.search_budget_degrade_standard_threshold == 0.1
        assert settings.search_budget_degrade_scraper_threshold == 0.05

    def test_feature_flag_defaults_off(self, settings):
        assert settings.search_quota_manager_enabled is False


@pytest.fixture()
def settings():
    """Get settings instance."""
    from app.core.config import get_settings

    return get_settings()
