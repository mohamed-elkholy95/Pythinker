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
