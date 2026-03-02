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
