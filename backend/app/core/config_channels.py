"""Channel gateway, cron scheduling, heartbeat, skills, and subagent settings mixin.

All features are **disabled by default** (False) to ensure zero impact on existing
deployments.  Enable via environment variables when ready to activate.
"""

from pydantic import Field


class ChannelSettingsMixin:
    """Multi-channel gateway, cron, heartbeat, skills, and subagent configuration."""

    # ── Global Gateway ────────────────────────────────────────────────────
    channel_gateway_enabled: bool = False
    channel_message_bus_size: int = 1000

    # ── Telegram ──────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_allowed_users: list[str] = Field(default_factory=list)
    telegram_webhook_mode: bool = False
    telegram_webhook_url: str = ""
    telegram_proxy_url: str = ""
    telegram_reuse_completed_sessions: bool = True
    telegram_session_idle_timeout_hours: int = 168
    telegram_max_context_turns: int = 50
    telegram_context_summarization_enabled: bool = True
    telegram_context_summarization_threshold_turns: int = 50
    telegram_pdf_delivery_enabled: bool = True
    telegram_pdf_message_min_chars: int = 3500
    telegram_pdf_report_min_chars: int = 2000
    telegram_pdf_caption_max_chars: int = 900
    telegram_pdf_async_threshold_chars: int = 10000
    telegram_pdf_cleanup_seconds: int = 600
    telegram_pdf_include_toc: bool = True
    telegram_pdf_toc_min_sections: int = 3
    telegram_pdf_unicode_font: str = "DejaVuSans"
    telegram_pdf_rate_limit_per_minute: int = 5
    telegram_pdf_file_id_cache_redis_enabled: bool = False
    telegram_pdf_max_generation_seconds: int = 30
    telegram_pdf_max_memory_mb: int = 100
    telegram_rate_limit_cooldown_seconds: int = 3
    telegram_max_messages_per_batch: int = 5

    # ── Discord ───────────────────────────────────────────────────────────
    discord_bot_token: str = ""
    discord_allowed_users: list[str] = Field(default_factory=list)
    discord_guild_ids: list[str] = Field(default_factory=list)

    # ── Slack ─────────────────────────────────────────────────────────────
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_allowed_users: list[str] = Field(default_factory=list)

    # ── Cron Scheduling ───────────────────────────────────────────────────
    cron_service_enabled: bool = False
    cron_max_jobs_per_user: int = 50
    cron_daily_budget_usd: float = 1.0

    # ── Heartbeat ─────────────────────────────────────────────────────────
    heartbeat_enabled: bool = False
    heartbeat_interval_minutes: int = 30

    # ── Skills System ─────────────────────────────────────────────────────
    skills_system_enabled: bool = False
    skills_workspace_dir: str = "~/.pythinker/skills"
    skills_builtin_enabled: bool = True

    # ── Subagent Spawning ─────────────────────────────────────────────────
    subagent_spawning_enabled: bool = False
    subagent_max_concurrent: int = 3
    subagent_max_iterations: int = 15
