"""Tests for FeatureFlags — agent enhancement feature toggle system."""

import os
from unittest.mock import patch

from app.core.feature_flags import FeatureFlags, get_feature_flags


class TestFeatureFlagsDefaults:
    """All flags default to False for safe deployment."""

    def test_all_defaults_false(self):
        with patch.dict(os.environ, {}, clear=True):
            flags = FeatureFlags(
                _env_file=None,  # type: ignore[call-arg]
            )
        assert flags.response_recovery_policy is False
        assert flags.failure_snapshot is False
        assert flags.tool_arg_canonicalization is False
        assert flags.duplicate_query_suppression is False
        assert flags.tool_definition_cache is False


class TestFeatureFlagsFromEnv:
    """Flags can be toggled via FEATURE_ prefix environment variables."""

    def test_enable_single_flag(self):
        with patch.dict(os.environ, {"FEATURE_RESPONSE_RECOVERY_POLICY": "true"}, clear=True):
            flags = FeatureFlags(_env_file=None)  # type: ignore[call-arg]
        assert flags.response_recovery_policy is True
        assert flags.failure_snapshot is False

    def test_enable_multiple_flags(self):
        env = {
            "FEATURE_FAILURE_SNAPSHOT": "true",
            "FEATURE_TOOL_DEFINITION_CACHE": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            flags = FeatureFlags(_env_file=None)  # type: ignore[call-arg]
        assert flags.failure_snapshot is True
        assert flags.tool_definition_cache is True
        assert flags.response_recovery_policy is False

    def test_false_string_disables_flag(self):
        with patch.dict(os.environ, {"FEATURE_FAILURE_SNAPSHOT": "false"}, clear=True):
            flags = FeatureFlags(_env_file=None)  # type: ignore[call-arg]
        assert flags.failure_snapshot is False


class TestLogEnabledFeatures:
    def test_logs_enabled_features(self, caplog):
        import logging

        with patch.dict(os.environ, {"FEATURE_FAILURE_SNAPSHOT": "true"}, clear=True):
            flags = FeatureFlags(_env_file=None)  # type: ignore[call-arg]
        with caplog.at_level(logging.INFO):
            flags.log_enabled_features()
        assert "failure_snapshot" in caplog.text

    def test_logs_all_disabled(self, caplog):
        import logging

        with patch.dict(os.environ, {}, clear=True):
            flags = FeatureFlags(_env_file=None)  # type: ignore[call-arg]
        with caplog.at_level(logging.INFO):
            flags.log_enabled_features()
        assert "disabled" in caplog.text


class TestGetFeatureFlags:
    def test_returns_instance(self):
        flags = get_feature_flags()
        assert isinstance(flags, FeatureFlags)

    def test_cached_singleton(self):
        f1 = get_feature_flags()
        f2 = get_feature_flags()
        assert f1 is f2
