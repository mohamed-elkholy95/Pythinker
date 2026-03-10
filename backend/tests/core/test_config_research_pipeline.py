"""Tests for ResearchPipelineSettingsMixin defaults and environment overrides."""

import pytest


@pytest.fixture()
def settings():
    """Get a fresh Settings instance (bypasses lru_cache)."""
    from app.core.config import Settings

    return Settings()


class TestFeatureFlagDefaults:
    """Pipeline feature flag defaults."""

    def test_pipeline_enabled_by_default(self, settings):
        assert settings.research_deterministic_pipeline_enabled is True

    def test_pipeline_mode_shadow_by_default(self, settings):
        assert settings.research_pipeline_mode == "shadow"


class TestSourceSelectionDefaults:
    """Source selection parameter defaults."""

    def test_source_select_count(self, settings):
        assert settings.research_source_select_count == 4

    def test_source_max_per_domain(self, settings):
        assert settings.research_source_max_per_domain == 1

    def test_source_allow_multi_page_domains(self, settings):
        assert settings.research_source_allow_multi_page_domains is True


class TestScoringWeightDefaults:
    """Source scoring weights must sum to 1.0 within tolerance."""

    def test_weight_relevance(self, settings):
        assert settings.research_weight_relevance == pytest.approx(0.35)

    def test_weight_authority(self, settings):
        assert settings.research_weight_authority == pytest.approx(0.25)

    def test_weight_freshness(self, settings):
        assert settings.research_weight_freshness == pytest.approx(0.20)

    def test_weight_rank(self, settings):
        assert settings.research_weight_rank == pytest.approx(0.20)

    def test_weights_sum_to_one(self, settings):
        total = (
            settings.research_weight_relevance
            + settings.research_weight_authority
            + settings.research_weight_freshness
            + settings.research_weight_rank
        )
        assert total == pytest.approx(1.0, abs=0.01)


class TestEvidenceAcquisitionDefaults:
    """Evidence acquisition parameter defaults."""

    def test_acquisition_concurrency(self, settings):
        assert settings.research_acquisition_concurrency == 4

    def test_acquisition_timeout_seconds(self, settings):
        assert settings.research_acquisition_timeout_seconds == pytest.approx(30.0)

    def test_excerpt_chars(self, settings):
        assert settings.research_excerpt_chars == 2000

    def test_full_content_offload(self, settings):
        assert settings.research_full_content_offload is True


class TestConfidenceThresholdDefaults:
    """Confidence and quality threshold defaults."""

    def test_soft_fail_verify_threshold(self, settings):
        assert settings.research_soft_fail_verify_threshold == 2

    def test_soft_fail_required_threshold(self, settings):
        assert settings.research_soft_fail_required_threshold == 3

    def test_thin_content_chars(self, settings):
        assert settings.research_thin_content_chars == 500

    def test_boilerplate_ratio_threshold(self, settings):
        assert settings.research_boilerplate_ratio_threshold == pytest.approx(0.6)


class TestSynthesisGateDefaults:
    """Default synthesis gate configuration."""

    def test_min_fetched_sources(self, settings):
        assert settings.research_min_fetched_sources == 3

    def test_min_high_confidence(self, settings):
        assert settings.research_min_high_confidence == 2

    def test_require_official_source(self, settings):
        assert settings.research_require_official_source is True

    def test_require_independent_source(self, settings):
        assert settings.research_require_independent_source is True


class TestRelaxedSynthesisGateDefaults:
    """Relaxed synthesis gate configuration (for niche topics)."""

    def test_relaxation_enabled(self, settings):
        assert settings.research_relaxation_enabled is True

    def test_relaxed_min_fetched_sources(self, settings):
        assert settings.research_relaxed_min_fetched_sources == 2

    def test_relaxed_min_high_confidence(self, settings):
        assert settings.research_relaxed_min_high_confidence == 1

    def test_relaxed_require_official_source(self, settings):
        assert settings.research_relaxed_require_official_source is False


class TestTelemetryDefaults:
    """Telemetry flag defaults."""

    def test_telemetry_enabled(self, settings):
        assert settings.research_telemetry_enabled is True


class TestEnvOverrides:
    """Verify fields can be loaded from environment variables."""

    def test_pipeline_disabled_from_env(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_DETERMINISTIC_PIPELINE_ENABLED", "false")
        from app.core.config import Settings

        s = Settings()
        assert s.research_deterministic_pipeline_enabled is False

    def test_pipeline_mode_enforced_from_env(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_PIPELINE_MODE", "enforced")
        from app.core.config import Settings

        s = Settings()
        assert s.research_pipeline_mode == "enforced"

    def test_source_select_count_from_env(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_SOURCE_SELECT_COUNT", "6")
        from app.core.config import Settings

        s = Settings()
        assert s.research_source_select_count == 6

    def test_min_fetched_sources_from_env(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_MIN_FETCHED_SOURCES", "2")
        from app.core.config import Settings

        s = Settings()
        assert s.research_min_fetched_sources == 2

    def test_require_official_source_disabled_from_env(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_REQUIRE_OFFICIAL_SOURCE", "false")
        from app.core.config import Settings

        s = Settings()
        assert s.research_require_official_source is False
