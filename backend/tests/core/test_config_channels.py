"""Tests for channel gateway, cron, heartbeat, skills, and subagent configuration."""

import pytest


@pytest.fixture()
def settings():
    """Get a fresh Settings instance (bypasses lru_cache)."""
    from app.core.config import Settings

    return Settings()


class TestChannelGatewayDefaults:
    """All channel features must be disabled by default."""

    def test_gateway_disabled_by_default(self, settings):
        assert settings.channel_gateway_enabled is False

    def test_message_bus_size_default(self, settings):
        assert settings.channel_message_bus_size == 1000


class TestTelegramDefaults:
    def test_bot_token_empty(self, settings):
        assert settings.telegram_bot_token == ""

    def test_allowed_users_empty_list(self, settings):
        assert settings.telegram_allowed_users == []

    def test_webhook_mode_disabled(self, settings):
        assert settings.telegram_webhook_mode is False

    def test_webhook_url_empty(self, settings):
        assert settings.telegram_webhook_url == ""

    def test_proxy_url_empty(self, settings):
        assert settings.telegram_proxy_url == ""

    def test_require_linked_account_disabled_by_default(self, settings):
        assert settings.telegram_require_linked_account is False

    def test_reuse_completed_sessions_enabled(self, settings):
        assert settings.telegram_reuse_completed_sessions is True

    def test_session_idle_timeout_hours_default(self, settings):
        assert settings.telegram_session_idle_timeout_hours == 168

    def test_context_turn_limits_defaults(self, settings):
        assert settings.telegram_max_context_turns == 50
        assert settings.telegram_context_summarization_enabled is True
        assert settings.telegram_context_summarization_threshold_turns == 50

    def test_pdf_delivery_defaults(self, settings):
        assert settings.telegram_pdf_delivery_enabled is True
        assert settings.telegram_pdf_force_long_text is False
        assert settings.telegram_pdf_message_min_chars == 3500
        assert settings.telegram_pdf_report_min_chars == 2000
        assert settings.telegram_pdf_caption_max_chars == 900
        assert settings.telegram_pdf_async_threshold_chars == 10000
        assert settings.telegram_pdf_cleanup_seconds == 600
        assert settings.telegram_pdf_include_toc is True
        assert settings.telegram_pdf_toc_min_sections == 3
        assert settings.telegram_pdf_unicode_font == "DejaVuSans"
        assert settings.telegram_pdf_rate_limit_per_minute == 5
        assert settings.telegram_pdf_file_id_cache_redis_enabled is False
        assert settings.telegram_pdf_max_generation_seconds == 30
        assert settings.telegram_pdf_max_memory_mb == 100

    def test_telegram_adapter_resilience_defaults(self, settings):
        assert settings.telegram_rate_limit_cooldown_seconds == 3
        assert settings.telegram_max_messages_per_batch == 5


class TestDiscordDefaults:
    def test_bot_token_empty(self, settings):
        assert settings.discord_bot_token == ""

    def test_allowed_users_empty_list(self, settings):
        assert settings.discord_allowed_users == []

    def test_guild_ids_empty_list(self, settings):
        assert settings.discord_guild_ids == []


class TestSlackDefaults:
    def test_bot_token_empty(self, settings):
        assert settings.slack_bot_token == ""

    def test_app_token_empty(self, settings):
        assert settings.slack_app_token == ""

    def test_allowed_users_empty_list(self, settings):
        assert settings.slack_allowed_users == []


class TestCronDefaults:
    def test_cron_disabled_by_default(self, settings):
        assert settings.cron_service_enabled is False

    def test_max_jobs_per_user(self, settings):
        assert settings.cron_max_jobs_per_user == 50

    def test_daily_budget_usd(self, settings):
        assert settings.cron_daily_budget_usd == 1.0


class TestHeartbeatDefaults:
    def test_heartbeat_disabled_by_default(self, settings):
        assert settings.heartbeat_enabled is False

    def test_interval_minutes(self, settings):
        assert settings.heartbeat_interval_minutes == 30


class TestSkillsSystemDefaults:
    def test_skills_disabled_by_default(self, settings):
        assert settings.skills_system_enabled is False

    def test_workspace_dir(self, settings):
        assert settings.skills_workspace_dir == "~/.pythinker/skills"

    def test_builtin_enabled(self, settings):
        assert settings.skills_builtin_enabled is True


class TestSubagentDefaults:
    def test_spawning_disabled_by_default(self, settings):
        assert settings.subagent_spawning_enabled is False

    def test_max_concurrent(self, settings):
        assert settings.subagent_max_concurrent == 3

    def test_max_iterations(self, settings):
        assert settings.subagent_max_iterations == 15


class TestChannelEnvOverride:
    """Verify fields can be loaded from environment variables."""

    def test_gateway_enabled_from_env(self, monkeypatch):
        monkeypatch.setenv("CHANNEL_GATEWAY_ENABLED", "true")
        from app.core.config import Settings

        s = Settings()
        assert s.channel_gateway_enabled is True

    def test_telegram_bot_token_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")
        from app.core.config import Settings

        s = Settings()
        assert s.telegram_bot_token == "123456:ABC-DEF"

    def test_telegram_require_linked_account_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_REQUIRE_LINKED_ACCOUNT", "true")
        from app.core.config import Settings

        s = Settings()
        assert s.telegram_require_linked_account is True

    def test_telegram_pdf_force_long_text_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_PDF_FORCE_LONG_TEXT", "true")
        from app.core.config import Settings

        s = Settings()
        assert s.telegram_pdf_force_long_text is True

    def test_cron_max_jobs_from_env(self, monkeypatch):
        monkeypatch.setenv("CRON_MAX_JOBS_PER_USER", "100")
        from app.core.config import Settings

        s = Settings()
        assert s.cron_max_jobs_per_user == 100

    def test_subagent_max_concurrent_from_env(self, monkeypatch):
        monkeypatch.setenv("SUBAGENT_MAX_CONCURRENT", "5")
        from app.core.config import Settings

        s = Settings()
        assert s.subagent_max_concurrent == 5
