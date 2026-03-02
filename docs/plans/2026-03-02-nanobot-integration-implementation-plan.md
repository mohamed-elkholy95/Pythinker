# Nanobot Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge nanobot as a vendored package into Pythinker, preserving all nanobot code as-is, and build thin integration bridges so Pythinker's AgentService can receive messages from Telegram, Discord, and other channels.

**Architecture:** Copy the entire `nanobot/` package (+ `bridge/`) into `backend/nanobot/` where Python can import it as `from nanobot.xxx`. Nanobot code stays untouched. Thin adapter files in Pythinker's DDD layers connect nanobot's MessageBus/channels to Pythinker's AgentService pipeline. Feature-flagged, off by default.

**Tech Stack:** python-telegram-bot 22.x, discord.py (raw gateway via websockets), croniter 6.x, litellm (already in nanobot), asyncio queues, MongoDB (existing)

---

## Pre-Implementation: Understand the Codebase

Before touching any code, read these files to understand existing patterns:

| File | Why |
|------|-----|
| `backend/app/core/config.py` | Mixin composition pattern for Settings |
| `backend/app/core/config_features.py` | Feature flag naming convention |
| `backend/app/domain/external/scraper.py` | Protocol + dataclass pattern to follow |
| `backend/app/domain/models/session.py` | Session model fields (need to add `source`) |
| `backend/app/domain/services/agent_task_runner.py` | Composition root — where new services wire in |
| `backend/app/application/services/agent_service.py` | `send_message()` entry point |
| `backend/app/domain/services/tools/dynamic_toolset.py` | Tool category + registration pattern |
| `nanobot-main/nanobot/bus/queue.py` | MessageBus to understand |
| `nanobot-main/nanobot/channels/base.py` | BaseChannel to understand |
| `nanobot-main/nanobot/channels/telegram.py` | Telegram adapter to understand |

---

## Task 1: Copy Nanobot Package Into Backend

**Files:**
- Create: `backend/nanobot/` (entire package tree)
- Create: `backend/nanobot/bridge/` (Node.js WhatsApp bridge)
- Modify: `backend/requirements.txt` (add nanobot deps)
- Modify: `backend/.gitignore` (if needed)

**Step 1: Copy nanobot package**

```bash
cp -r nanobot-main/nanobot backend/nanobot
```

This places the package at `backend/nanobot/` which becomes `/app/nanobot/` in Docker (WORKDIR is `/app/`). All `from nanobot.xxx` imports work because Python searches the working directory.

**Step 2: Copy bridge directory into nanobot package**

```bash
cp -r nanobot-main/bridge backend/nanobot/bridge
```

This matches what `hatch` does when building the wheel (`"bridge" = "nanobot/bridge"`).

**Step 3: Copy nanobot tests**

```bash
cp -r nanobot-main/tests backend/tests/nanobot
```

**Step 4: Verify imports work**

```bash
cd backend && python -c "from nanobot.agent.loop import AgentLoop; print('OK:', AgentLoop)"
cd backend && python -c "from nanobot.channels.telegram import TelegramChannel; print('OK')"
cd backend && python -c "from nanobot.cron.service import CronService; print('OK')"
cd backend && python -c "from nanobot.bus.queue import MessageBus; print('OK')"
```

Expected: All print OK. If import errors, install missing deps (Step 5).

**Step 5: Add nanobot-specific dependencies to requirements.txt**

Add these lines to `backend/requirements.txt` (only deps not already present):

```
# Nanobot integration — channel adapters & scheduling
litellm>=1.81.5
croniter>=6.0.0
python-telegram-bot[socks]>=22.0
slack-sdk>=3.39.0
dingtalk-stream>=0.24.0
lark-oapi>=1.5.0
python-socketio>=5.16.0
qq-botpy>=1.2.0
slackify-markdown>=0.2.0
readability-lxml>=0.8.4
loguru>=0.7.3
json-repair>=0.57.0
oauth-cli-kit>=0.1.3
socksio>=1.0.0
python-socks[asyncio]>=2.8.0
prompt-toolkit>=3.0.50
msgpack>=1.1.0
websocket-client>=1.9.0
```

**Step 6: Verify full import chain**

```bash
cd backend && python -c "
from nanobot.agent.loop import AgentLoop
from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader
from nanobot.agent.subagent import SubagentManager
from nanobot.bus.queue import MessageBus
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.channels.base import BaseChannel
from nanobot.channels.manager import ChannelManager
from nanobot.channels.telegram import TelegramChannel
from nanobot.channels.discord import DiscordChannel
from nanobot.cron.service import CronService
from nanobot.heartbeat.service import HeartbeatService
from nanobot.config.schema import Config
from nanobot.providers.base import LLMProvider
print('All nanobot imports OK')
"
```

Expected: `All nanobot imports OK`

**Step 7: Run nanobot's own tests**

```bash
cd backend && python -m pytest tests/nanobot/ -v --tb=short 2>&1 | head -50
```

Expected: Tests pass (or skip if they need live services).

**Step 8: Run existing Pythinker tests (regression check)**

```bash
cd backend && conda activate pythinker && pytest tests/ -x --ignore=tests/nanobot -q 2>&1 | tail -20
```

Expected: All existing tests pass. No regressions from adding nanobot package.

**Step 9: Commit**

```bash
git add backend/nanobot/ backend/tests/nanobot/ backend/requirements.txt
git commit -m "chore(nanobot): vendor nanobot package into backend

Copy nanobot v0.1.4.post3 as-is into backend/nanobot/ for direct import.
Includes bridge/, skills/, templates/. Add channel/cron dependencies."
```

---

## Task 2: Configuration — Channel & Cron Settings

**Files:**
- Create: `backend/app/core/config_channels.py`
- Modify: `backend/app/core/config.py` (add mixin to Settings)
- Modify: `backend/.env.example` (add channel env vars)

**Step 1: Write failing test for config loading**

Create `backend/tests/core/test_config_channels.py`:

```python
"""Tests for channel and cron configuration settings."""
import pytest
from unittest.mock import patch


def test_channel_settings_defaults():
    """All channel features are disabled by default."""
    from app.core.config_channels import ChannelSettingsMixin

    # ChannelSettingsMixin should have these fields with defaults
    assert ChannelSettingsMixin.__annotations__["channel_gateway_enabled"]
    instance = type("S", (ChannelSettingsMixin,), {})()
    assert instance.channel_gateway_enabled is False
    assert instance.telegram_bot_token == ""
    assert instance.discord_bot_token == ""
    assert instance.cron_service_enabled is False
    assert instance.skills_system_enabled is False
    assert instance.subagent_spawning_enabled is False


def test_channel_settings_from_env():
    """Channel settings load from environment variables."""
    env = {
        "CHANNEL_GATEWAY_ENABLED": "true",
        "TELEGRAM_BOT_TOKEN": "123:ABC",
        "TELEGRAM_ALLOWED_USERS": "111,222,333",
        "DISCORD_BOT_TOKEN": "discord-token-xyz",
        "CRON_SERVICE_ENABLED": "true",
    }
    with patch.dict("os.environ", env, clear=False):
        from app.core.config import get_settings
        settings = get_settings()
        assert settings.channel_gateway_enabled is True
        assert settings.telegram_bot_token == "123:ABC"
        assert settings.telegram_allowed_users == ["111", "222", "333"]
        assert settings.discord_bot_token == "discord-token-xyz"
        assert settings.cron_service_enabled is True


def test_channel_settings_empty_allowed_users_denies_all():
    """Empty allowed_users list means deny all (security default)."""
    from app.core.config_channels import ChannelSettingsMixin
    instance = type("S", (ChannelSettingsMixin,), {})()
    assert instance.telegram_allowed_users == []
    assert instance.discord_allowed_users == []
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/core/test_config_channels.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.config_channels'`

**Step 3: Create config_channels.py**

Create `backend/app/core/config_channels.py`:

```python
"""Channel gateway, cron scheduling, skills, and subagent configuration."""

from __future__ import annotations


class ChannelSettingsMixin:
    """Multi-channel gateway settings.

    All features are OFF by default — zero impact on existing deployments.
    Enable via environment variables.
    """

    # ── Global Gateway ──────────────────────────────────────────────
    channel_gateway_enabled: bool = False
    channel_message_bus_size: int = 1000

    # ── Telegram ────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_allowed_users: list[str] = []
    telegram_webhook_mode: bool = False
    telegram_webhook_url: str = ""
    telegram_proxy_url: str = ""

    # ── Discord ─────────────────────────────────────────────────────
    discord_bot_token: str = ""
    discord_allowed_users: list[str] = []
    discord_guild_ids: list[str] = []

    # ── Slack ───────────────────────────────────────────────────────
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_allowed_users: list[str] = []

    # ── Cron Scheduling ─────────────────────────────────────────────
    cron_service_enabled: bool = False
    cron_max_jobs_per_user: int = 50
    cron_daily_budget_usd: float = 1.0

    # ── Heartbeat ───────────────────────────────────────────────────
    heartbeat_enabled: bool = False
    heartbeat_interval_minutes: int = 30

    # ── Skills System ───────────────────────────────────────────────
    skills_system_enabled: bool = False
    skills_workspace_dir: str = "~/.pythinker/skills"
    skills_builtin_enabled: bool = True

    # ── Subagent Spawning ───────────────────────────────────────────
    subagent_spawning_enabled: bool = False
    subagent_max_concurrent: int = 3
    subagent_max_iterations: int = 15
```

**Step 4: Add mixin to Settings class**

In `backend/app/core/config.py`, add the import and mixin:

```python
# In the import block (around line 42-66):
from app.core.config_channels import ChannelSettingsMixin

# In the Settings class (before BaseSettings, around line 107):
class Settings(
    # ... existing mixins ...
    ChannelSettingsMixin,  # Add before BaseSettings
    BaseSettings,
):
```

**Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/core/test_config_channels.py -v
```

Expected: PASS

**Step 6: Update .env.example**

Add to `backend/.env.example`:

```bash
# ── Channel Gateway ─────────────────────────────────────────────
# CHANNEL_GATEWAY_ENABLED=false
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_ALLOWED_USERS=          # Comma-separated sender IDs
# DISCORD_BOT_TOKEN=
# DISCORD_ALLOWED_USERS=
# DISCORD_GUILD_IDS=
# SLACK_BOT_TOKEN=
# SLACK_APP_TOKEN=

# ── Cron Scheduling ─────────────────────────────────────────────
# CRON_SERVICE_ENABLED=false
# CRON_MAX_JOBS_PER_USER=50
# CRON_DAILY_BUDGET_USD=1.0

# ── Heartbeat ───────────────────────────────────────────────────
# HEARTBEAT_ENABLED=false
# HEARTBEAT_INTERVAL_MINUTES=30

# ── Skills System ───────────────────────────────────────────────
# SKILLS_SYSTEM_ENABLED=false
# SKILLS_WORKSPACE_DIR=~/.pythinker/skills

# ── Subagent Spawning ──────────────────────────────────────────
# SUBAGENT_SPAWNING_ENABLED=false
# SUBAGENT_MAX_CONCURRENT=3
```

**Step 7: Run full test suite (regression)**

```bash
cd backend && pytest tests/ -x --ignore=tests/nanobot -q 2>&1 | tail -10
```

Expected: All existing tests pass.

**Step 8: Commit**

```bash
git add backend/app/core/config_channels.py backend/app/core/config.py \
        backend/.env.example backend/tests/core/test_config_channels.py
git commit -m "feat(channels): add channel gateway configuration settings

ChannelSettingsMixin with Telegram, Discord, Slack, Cron, Heartbeat,
Skills, and Subagent settings. All features disabled by default."
```

---

## Task 3: Domain Models — Channel Messages & Scheduled Jobs

**Files:**
- Create: `backend/app/domain/models/channel.py`
- Create: `backend/app/domain/models/scheduled_job.py`
- Modify: `backend/app/domain/models/session.py` (add `source` field)
- Test: `backend/tests/domain/models/test_channel_models.py`

**Step 1: Write failing tests**

Create `backend/tests/domain/models/test_channel_models.py`:

```python
"""Tests for channel domain models."""
import pytest
from datetime import datetime, UTC


def test_channel_type_enum():
    from app.domain.models.channel import ChannelType
    assert ChannelType.TELEGRAM == "telegram"
    assert ChannelType.DISCORD == "discord"
    assert ChannelType.WEB == "web"
    assert ChannelType.CRON == "cron"


def test_inbound_message_creation():
    from app.domain.models.channel import ChannelType, InboundMessage
    msg = InboundMessage(
        channel=ChannelType.TELEGRAM,
        sender_id="123456",
        chat_id="789",
        content="Hello Pythinker",
    )
    assert msg.channel == ChannelType.TELEGRAM
    assert msg.content == "Hello Pythinker"
    assert msg.media == []
    assert msg.timestamp is not None


def test_outbound_message_creation():
    from app.domain.models.channel import ChannelType, OutboundMessage
    msg = OutboundMessage(
        channel=ChannelType.DISCORD,
        chat_id="guild-123",
        content="Here are the results...",
    )
    assert msg.channel == ChannelType.DISCORD
    assert msg.reply_to is None


def test_user_channel_link():
    from app.domain.models.channel import ChannelType, UserChannelLink
    link = UserChannelLink(
        user_id="pythinker-user-1",
        channel=ChannelType.TELEGRAM,
        sender_id="tg-123456",
        chat_id="tg-789",
        display_name="John",
    )
    assert link.user_id == "pythinker-user-1"
    assert link.linked_at is not None


def test_scheduled_job_creation():
    from app.domain.models.scheduled_job import ScheduledJob
    job = ScheduledJob(
        user_id="user-1",
        schedule_type="cron",
        schedule_expr="0 9 * * *",
        task_description="Generate daily report",
        timezone="America/New_York",
    )
    assert job.enabled is True
    assert job.run_count == 0
    assert job.id  # Auto-generated


def test_session_source_field():
    from app.domain.models.session import Session
    session = Session(
        user_id="u1",
        agent_id="a1",
        source="telegram",
    )
    assert session.source == "telegram"


def test_session_source_defaults_to_web():
    from app.domain.models.session import Session
    session = Session(user_id="u1", agent_id="a1")
    assert session.source == "web"
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/domain/models/test_channel_models.py -v
```

Expected: FAIL

**Step 3: Create channel.py domain model**

Create `backend/app/domain/models/channel.py`:

```python
"""Channel gateway domain models.

These models represent messages flowing between external chat platforms
and Pythinker's agent system. They are channel-agnostic — the domain
layer never knows about Telegram/Discord specifics.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ChannelType(StrEnum):
    """Supported communication channels."""

    WEB = "web"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    CRON = "cron"
    API = "api"


class MediaAttachment(BaseModel):
    """Media file attached to a channel message."""

    url: str
    mime_type: str = ""
    filename: str = ""
    size_bytes: int = 0


class InboundMessage(BaseModel):
    """Message received from an external channel."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    channel: ChannelType
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    media: list[MediaAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_key_override: str | None = None


class OutboundMessage(BaseModel):
    """Message to send to an external channel."""

    channel: ChannelType
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[MediaAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserChannelLink(BaseModel):
    """Maps an external channel identity to a Pythinker user."""

    user_id: str
    channel: ChannelType
    sender_id: str
    chat_id: str
    display_name: str | None = None
    linked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

**Step 4: Create scheduled_job.py domain model**

Create `backend/app/domain/models/scheduled_job.py`:

```python
"""Scheduled job domain model for cron-based agent tasks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.models.channel import ChannelType


class ScheduledJob(BaseModel):
    """A scheduled task that triggers agent execution on a cron/interval."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str
    schedule_type: Literal["cron", "interval", "once"]
    schedule_expr: str
    task_description: str
    channel: ChannelType | None = None
    chat_id: str | None = None
    timezone: str = "UTC"
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    max_runs: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

**Step 5: Add `source` field to Session model**

In `backend/app/domain/models/session.py`, add after `user_id`:

```python
    source: str = "web"  # "web" | "telegram" | "discord" | "cron" | "api"
```

**Step 6: Run tests**

```bash
cd backend && pytest tests/domain/models/test_channel_models.py -v
```

Expected: All PASS

**Step 7: Regression check**

```bash
cd backend && pytest tests/ -x --ignore=tests/nanobot -q 2>&1 | tail -10
```

Expected: All pass (source field has default, no breaking change).

**Step 8: Commit**

```bash
git add backend/app/domain/models/channel.py \
        backend/app/domain/models/scheduled_job.py \
        backend/app/domain/models/session.py \
        backend/tests/domain/models/test_channel_models.py
git commit -m "feat(channels): add channel and scheduled job domain models

ChannelType enum, InboundMessage, OutboundMessage, UserChannelLink,
ScheduledJob, and Session.source field for multi-channel support."
```

---

## Task 4: Domain Protocol — Channel Gateway Interface

**Files:**
- Create: `backend/app/domain/external/channel_gateway.py`
- Test: `backend/tests/domain/external/test_channel_gateway.py`

**Step 1: Write failing test**

Create `backend/tests/domain/external/test_channel_gateway.py`:

```python
"""Tests for channel gateway protocol."""
import pytest
from unittest.mock import AsyncMock

from app.domain.external.channel_gateway import ChannelGateway
from app.domain.models.channel import ChannelType, OutboundMessage


@pytest.mark.asyncio
async def test_channel_gateway_protocol_compliance():
    """Any class implementing ChannelGateway protocol must have these methods."""
    class MockGateway:
        async def start(self) -> None: ...
        async def stop(self) -> None: ...
        async def send_to_channel(self, message: OutboundMessage) -> None: ...
        def get_active_channels(self) -> list[ChannelType]: ...

    gw = MockGateway()
    assert isinstance(gw, ChannelGateway)


@pytest.mark.asyncio
async def test_non_conforming_class_fails_protocol():
    """A class missing methods does not satisfy the protocol."""
    class BadGateway:
        async def start(self) -> None: ...

    gw = BadGateway()
    assert not isinstance(gw, ChannelGateway)
```

**Step 2: Run test to verify failure**

```bash
cd backend && pytest tests/domain/external/test_channel_gateway.py -v
```

**Step 3: Create the protocol**

Create `backend/app/domain/external/channel_gateway.py`:

```python
"""Channel gateway protocol — domain-layer contract for multi-channel messaging.

Infrastructure adapters (Telegram, Discord, etc.) implement this protocol.
The domain layer depends only on this abstraction, never on concrete channels.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.channel import ChannelType, OutboundMessage


@runtime_checkable
class ChannelGateway(Protocol):
    """Gateway for sending messages to external channels."""

    async def start(self) -> None:
        """Start all configured channel adapters."""
        ...

    async def stop(self) -> None:
        """Gracefully stop all channel adapters."""
        ...

    async def send_to_channel(self, message: OutboundMessage) -> None:
        """Send a message to a specific channel."""
        ...

    def get_active_channels(self) -> list[ChannelType]:
        """Return list of currently active channel types."""
        ...
```

**Step 4: Run tests**

```bash
cd backend && pytest tests/domain/external/test_channel_gateway.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/external/channel_gateway.py \
        backend/tests/domain/external/test_channel_gateway.py
git commit -m "feat(channels): add ChannelGateway domain protocol

Runtime-checkable protocol for multi-channel messaging abstraction.
Infrastructure adapters implement this contract."
```

---

## Task 5: Integration Bridge — MessageRouter

This is the **key bridge** between nanobot's channel system and Pythinker's AgentService.

**Files:**
- Create: `backend/app/domain/services/channels/message_router.py`
- Create: `backend/app/domain/services/channels/__init__.py`
- Test: `backend/tests/domain/services/channels/test_message_router.py`

**Step 1: Write failing test**

Create `backend/tests/domain/services/channels/test_message_router.py`:

```python
"""Tests for MessageRouter — bridges nanobot channels to Pythinker AgentService."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

from app.domain.models.channel import ChannelType, InboundMessage, OutboundMessage


@pytest.mark.asyncio
async def test_route_inbound_creates_session_and_sends_message():
    """Inbound channel message creates a session and calls AgentService."""
    from app.domain.services.channels.message_router import MessageRouter

    mock_agent_service = AsyncMock()
    mock_agent_service.create_session.return_value = MagicMock(id="sess-123")
    mock_agent_service.send_message.return_value = iter([])  # empty event stream

    mock_user_repo = AsyncMock()
    mock_user_repo.get_user_by_channel.return_value = "pythinker-user-1"

    router = MessageRouter(
        agent_service=mock_agent_service,
        user_channel_repo=mock_user_repo,
    )

    msg = InboundMessage(
        channel=ChannelType.TELEGRAM,
        sender_id="tg-123",
        chat_id="tg-chat-456",
        content="Find best laptop under $1000",
    )

    outbound_messages = []
    async for out_msg in router.route_inbound(msg):
        outbound_messages.append(out_msg)

    mock_user_repo.get_user_by_channel.assert_called_once_with(
        ChannelType.TELEGRAM, "tg-123"
    )
    mock_agent_service.create_session.assert_called_once()


@pytest.mark.asyncio
async def test_route_inbound_unknown_user_auto_registers():
    """Unknown sender gets auto-registered with a new Pythinker user."""
    from app.domain.services.channels.message_router import MessageRouter

    mock_agent_service = AsyncMock()
    mock_agent_service.create_session.return_value = MagicMock(id="sess-new")
    mock_agent_service.send_message.return_value = iter([])

    mock_user_repo = AsyncMock()
    mock_user_repo.get_user_by_channel.return_value = None  # Unknown user
    mock_user_repo.create_channel_user.return_value = "auto-user-789"

    router = MessageRouter(
        agent_service=mock_agent_service,
        user_channel_repo=mock_user_repo,
    )

    msg = InboundMessage(
        channel=ChannelType.DISCORD,
        sender_id="dc-unknown",
        chat_id="dc-guild",
        content="Hello",
    )

    async for _ in router.route_inbound(msg):
        pass

    mock_user_repo.create_channel_user.assert_called_once()


@pytest.mark.asyncio
async def test_route_slash_command_new():
    """The /new command clears the session."""
    from app.domain.services.channels.message_router import MessageRouter

    mock_agent_service = AsyncMock()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_user_by_channel.return_value = "user-1"

    router = MessageRouter(
        agent_service=mock_agent_service,
        user_channel_repo=mock_user_repo,
    )

    msg = InboundMessage(
        channel=ChannelType.TELEGRAM,
        sender_id="tg-123",
        chat_id="tg-456",
        content="/new",
    )

    results = []
    async for out in router.route_inbound(msg):
        results.append(out)

    # /new should return a confirmation, not call send_message
    assert len(results) >= 1
    assert "new session" in results[0].content.lower() or "cleared" in results[0].content.lower()
```

**Step 2: Run test to verify failure**

```bash
cd backend && pytest tests/domain/services/channels/test_message_router.py -v
```

**Step 3: Implement MessageRouter**

Create `backend/app/domain/services/channels/__init__.py` (empty).

Create `backend/app/domain/services/channels/message_router.py`:

```python
"""MessageRouter — bridges external channel messages to Pythinker's AgentService.

This is the central integration point between nanobot's channel system and
Pythinker's agent pipeline. Inbound messages are routed to AgentService,
and agent events are converted to outbound channel messages.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Protocol

from app.domain.models.channel import (
    ChannelType,
    InboundMessage,
    OutboundMessage,
)

if TYPE_CHECKING:
    from app.application.services.agent_service import AgentService

logger = logging.getLogger(__name__)


class UserChannelRepository(Protocol):
    """Repository for user-channel identity mapping."""

    async def get_user_by_channel(
        self, channel: ChannelType, sender_id: str
    ) -> str | None:
        """Find Pythinker user_id by channel sender. Returns None if unknown."""
        ...

    async def create_channel_user(
        self, channel: ChannelType, sender_id: str, chat_id: str
    ) -> str:
        """Create a new Pythinker user for a channel sender. Returns user_id."""
        ...

    async def get_session_key(
        self, user_id: str, channel: ChannelType, chat_id: str
    ) -> str | None:
        """Get active session ID for this user+channel+chat combo."""
        ...

    async def set_session_key(
        self, user_id: str, channel: ChannelType, chat_id: str, session_id: str
    ) -> None:
        """Store active session ID for this user+channel+chat combo."""
        ...


# Slash commands handled by the router (not forwarded to agent)
_SLASH_COMMANDS = {"/new", "/stop", "/help", "/status"}


class MessageRouter:
    """Routes inbound channel messages to Pythinker's AgentService.

    Yields OutboundMessage objects for each agent event that should be
    sent back to the originating channel.
    """

    def __init__(
        self,
        agent_service: AgentService,
        user_channel_repo: UserChannelRepository,
    ) -> None:
        self._agent_service = agent_service
        self._user_repo = user_channel_repo

    async def route_inbound(
        self, message: InboundMessage
    ) -> AsyncGenerator[OutboundMessage, None]:
        """Route an inbound channel message through the agent pipeline.

        Yields OutboundMessage objects as the agent produces events.
        """
        # Resolve or create user
        user_id = await self._user_repo.get_user_by_channel(
            message.channel, message.sender_id
        )
        if user_id is None:
            user_id = await self._user_repo.create_channel_user(
                message.channel, message.sender_id, message.chat_id
            )
            logger.info(
                "Auto-registered channel user: %s/%s -> %s",
                message.channel, message.sender_id, user_id,
            )

        # Handle slash commands locally
        content = message.content.strip()
        if content.split()[0].lower() in _SLASH_COMMANDS if content else False:
            async for out in self._handle_slash_command(
                content, message, user_id
            ):
                yield out
            return

        # Get or create session for this channel conversation
        session_id = await self._user_repo.get_session_key(
            user_id, message.channel, message.chat_id
        )
        if session_id is None:
            session = await self._agent_service.create_session(
                user_id=user_id,
                initial_message=content,
                source=message.channel.value,
            )
            session_id = session.id
            await self._user_repo.set_session_key(
                user_id, message.channel, message.chat_id, session_id
            )
            logger.info("Created new session %s for %s", session_id, message.channel)

        # Stream agent events and convert to outbound messages
        try:
            async for event in self._agent_service.send_message(
                session_id=session_id,
                user_id=user_id,
                message=content,
            ):
                out = self._event_to_outbound(event, message)
                if out is not None:
                    yield out
        except Exception:
            logger.exception("Error processing channel message")
            yield OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content="Sorry, an error occurred while processing your request.",
            )

    def _event_to_outbound(
        self, event: Any, source: InboundMessage
    ) -> OutboundMessage | None:
        """Convert a Pythinker agent event to a channel outbound message.

        Returns None for events that shouldn't be sent to the channel
        (e.g., internal plan steps, tool calls).
        """
        event_type = getattr(event, "type", None)

        # Only send substantial content events to channels
        if event_type == "message":
            content = getattr(event, "content", "") or ""
            if content.strip():
                return OutboundMessage(
                    channel=source.channel,
                    chat_id=source.chat_id,
                    content=content,
                )
        elif event_type == "report":
            content = getattr(event, "content", "") or getattr(event, "report", "")
            if content.strip():
                return OutboundMessage(
                    channel=source.channel,
                    chat_id=source.chat_id,
                    content=content,
                )
        elif event_type == "error":
            error = getattr(event, "error", "An error occurred")
            return OutboundMessage(
                channel=source.channel,
                chat_id=source.chat_id,
                content=f"Error: {error}",
            )

        return None

    async def _handle_slash_command(
        self,
        content: str,
        message: InboundMessage,
        user_id: str,
    ) -> AsyncGenerator[OutboundMessage, None]:
        """Handle channel-specific slash commands."""
        cmd = content.split()[0].lower()

        if cmd == "/new":
            # Clear session mapping so next message creates a new session
            await self._user_repo.set_session_key(
                user_id, message.channel, message.chat_id, ""
            )
            yield OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content="Session cleared. Send a new message to start fresh.",
            )

        elif cmd == "/help":
            yield OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content=(
                    "Available commands:\n"
                    "/new - Start a new session\n"
                    "/stop - Cancel current task\n"
                    "/status - Show current session status\n"
                    "/help - Show this help message"
                ),
            )

        elif cmd == "/status":
            session_id = await self._user_repo.get_session_key(
                user_id, message.channel, message.chat_id
            )
            status = f"Active session: {session_id}" if session_id else "No active session"
            yield OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content=status,
            )

        elif cmd == "/stop":
            yield OutboundMessage(
                channel=message.channel,
                chat_id=message.chat_id,
                content="Task cancellation requested.",
            )
```

**Step 4: Run tests**

```bash
cd backend && pytest tests/domain/services/channels/test_message_router.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/channels/ \
        backend/tests/domain/services/channels/
git commit -m "feat(channels): add MessageRouter bridge service

Routes inbound channel messages to AgentService.send_message() and
converts agent events to outbound channel messages. Handles /new,
/stop, /help, /status slash commands. Auto-registers unknown users."
```

---

## Task 6: Infrastructure — Nanobot Channel Adapter Bridge

This wraps nanobot's existing ChannelManager to implement Pythinker's ChannelGateway protocol.

**Files:**
- Create: `backend/app/infrastructure/external/channels/__init__.py`
- Create: `backend/app/infrastructure/external/channels/nanobot_gateway.py`
- Test: `backend/tests/infrastructure/external/channels/test_nanobot_gateway.py`

**Step 1: Write failing test**

Create `backend/tests/infrastructure/external/channels/test_nanobot_gateway.py`:

```python
"""Tests for NanobotGateway — wraps nanobot's ChannelManager for Pythinker."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.external.channel_gateway import ChannelGateway
from app.domain.models.channel import ChannelType


def test_nanobot_gateway_satisfies_protocol():
    """NanobotGateway implements ChannelGateway protocol."""
    from app.infrastructure.external.channels.nanobot_gateway import NanobotGateway
    assert issubclass(NanobotGateway, ChannelGateway) or isinstance(
        NanobotGateway.__new__(NanobotGateway), ChannelGateway
    )


@pytest.mark.asyncio
async def test_gateway_start_initializes_nanobot_channels():
    """Starting gateway initializes nanobot's MessageBus and channels."""
    from app.infrastructure.external.channels.nanobot_gateway import NanobotGateway

    with patch("app.infrastructure.external.channels.nanobot_gateway.MessageBus") as MockBus, \
         patch("app.infrastructure.external.channels.nanobot_gateway.ChannelManager") as MockMgr:

        mock_bus = MockBus.return_value
        mock_mgr = AsyncMock()
        MockMgr.return_value = mock_mgr

        gw = NanobotGateway(
            telegram_token="test-token",
            telegram_allowed=["123"],
            message_router=AsyncMock(),
        )
        await gw.start()
        mock_mgr.start.assert_called_once()


@pytest.mark.asyncio
async def test_gateway_get_active_channels():
    """Active channels returns list of configured channel types."""
    from app.infrastructure.external.channels.nanobot_gateway import NanobotGateway

    gw = NanobotGateway(
        telegram_token="test-token",
        telegram_allowed=["123"],
        message_router=AsyncMock(),
    )
    channels = gw.get_active_channels()
    assert ChannelType.TELEGRAM in channels
```

**Step 2: Run to verify failure**

```bash
cd backend && pytest tests/infrastructure/external/channels/test_nanobot_gateway.py -v
```

**Step 3: Implement NanobotGateway**

Create `backend/app/infrastructure/external/channels/__init__.py` (empty).

Create `backend/app/infrastructure/external/channels/nanobot_gateway.py`:

```python
"""NanobotGateway — wraps nanobot's channel system for Pythinker integration.

This adapter bridges nanobot's MessageBus + ChannelManager to Pythinker's
ChannelGateway protocol. Nanobot code runs as-is; this file only handles
the interface translation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from nanobot.bus.events import InboundMessage as NbInbound
from nanobot.bus.events import OutboundMessage as NbOutbound
from nanobot.bus.queue import MessageBus
from nanobot.channels.manager import ChannelManager
from nanobot.config.schema import (
    ChannelsConfig,
    Config,
    DiscordConfig,
    SlackConfig,
    TelegramConfig,
)

from app.domain.models.channel import (
    ChannelType,
    InboundMessage,
    OutboundMessage,
)

if TYPE_CHECKING:
    from app.domain.services.channels.message_router import MessageRouter

logger = logging.getLogger(__name__)


# Map nanobot channel names → Pythinker ChannelType
_CHANNEL_MAP: dict[str, ChannelType] = {
    "telegram": ChannelType.TELEGRAM,
    "discord": ChannelType.DISCORD,
    "slack": ChannelType.SLACK,
    "whatsapp": ChannelType.WHATSAPP,
    "email": ChannelType.EMAIL,
}


class NanobotGateway:
    """Wraps nanobot's ChannelManager to serve as Pythinker's ChannelGateway.

    Nanobot's code runs unmodified. This adapter:
    1. Creates a nanobot Config from Pythinker's settings
    2. Starts nanobot's ChannelManager with MessageBus
    3. Consumes inbound messages from the bus → forwards to MessageRouter
    4. Receives outbound from MessageRouter → publishes to bus for delivery
    """

    def __init__(
        self,
        message_router: MessageRouter,
        telegram_token: str = "",
        telegram_allowed: list[str] | None = None,
        discord_token: str = "",
        discord_allowed: list[str] | None = None,
        slack_bot_token: str = "",
        slack_app_token: str = "",
        slack_allowed: list[str] | None = None,
    ) -> None:
        self._router = message_router
        self._bus = MessageBus()
        self._running = False
        self._consumer_task: asyncio.Task[None] | None = None

        # Build nanobot config from Pythinker settings
        channels_cfg = ChannelsConfig()
        if telegram_token:
            channels_cfg.telegram = TelegramConfig(
                token=telegram_token,
                allowFrom=telegram_allowed or [],
            )
        if discord_token:
            channels_cfg.discord = DiscordConfig(
                token=discord_token,
                allowFrom=discord_allowed or [],
            )
        if slack_bot_token:
            channels_cfg.slack = SlackConfig(
                botToken=slack_bot_token,
                appToken=slack_app_token,
                allowFrom=slack_allowed or [],
            )

        self._config = Config(channels=channels_cfg)
        self._channel_manager = ChannelManager(
            config=self._config,
            bus=self._bus,
        )

    async def start(self) -> None:
        """Start nanobot channel adapters and message consumer."""
        if self._running:
            return
        self._running = True

        await self._channel_manager.start()
        self._consumer_task = asyncio.create_task(
            self._consume_inbound(), name="nanobot-inbound-consumer"
        )
        logger.info(
            "NanobotGateway started with channels: %s",
            self.get_active_channels(),
        )

    async def stop(self) -> None:
        """Stop all channels and consumer task."""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        await self._channel_manager.stop()
        logger.info("NanobotGateway stopped")

    async def send_to_channel(self, message: OutboundMessage) -> None:
        """Send a Pythinker outbound message via nanobot's channel system."""
        nb_msg = NbOutbound(
            channel=message.channel.value,
            chat_id=message.chat_id,
            content=message.content,
            reply_to=message.reply_to,
            metadata=message.metadata,
        )
        await self._bus.publish_outbound(nb_msg)

    def get_active_channels(self) -> list[ChannelType]:
        """Return list of configured and active channel types."""
        active: list[ChannelType] = []
        cfg = self._config.channels
        if cfg.telegram and cfg.telegram.token:
            active.append(ChannelType.TELEGRAM)
        if cfg.discord and cfg.discord.token:
            active.append(ChannelType.DISCORD)
        if cfg.slack and cfg.slack.botToken:
            active.append(ChannelType.SLACK)
        return active

    async def _consume_inbound(self) -> None:
        """Consume messages from nanobot's bus and forward to MessageRouter."""
        while self._running:
            try:
                nb_msg: NbInbound = await self._bus.consume_inbound()

                # Convert nanobot InboundMessage → Pythinker InboundMessage
                channel = _CHANNEL_MAP.get(nb_msg.channel, ChannelType.WEB)
                pt_msg = InboundMessage(
                    channel=channel,
                    sender_id=nb_msg.sender_id,
                    chat_id=nb_msg.chat_id,
                    content=nb_msg.content,
                    metadata=nb_msg.metadata or {},
                )

                # Route through Pythinker and collect outbound responses
                async for outbound in self._router.route_inbound(pt_msg):
                    await self.send_to_channel(outbound)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error consuming inbound message")
                await asyncio.sleep(1)  # Backoff on error
```

**Step 4: Run tests**

```bash
cd backend && pytest tests/infrastructure/external/channels/test_nanobot_gateway.py -v
```

Expected: PASS (may need mock adjustments based on exact nanobot constructor signatures)

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/channels/ \
        backend/tests/infrastructure/external/channels/
git commit -m "feat(channels): add NanobotGateway infrastructure adapter

Wraps nanobot's ChannelManager + MessageBus to implement Pythinker's
ChannelGateway protocol. Nanobot code runs unmodified. Bridges
inbound/outbound messages between the two systems."
```

---

## Task 7: Gateway Runner — Startup Entry Point

**Files:**
- Create: `backend/app/interfaces/gateway/__init__.py`
- Create: `backend/app/interfaces/gateway/gateway_runner.py`
- Modify: `backend/docker-compose.yml` (add gateway service, optional)

**Step 1: Create gateway runner**

Create `backend/app/interfaces/gateway/__init__.py` (empty).

Create `backend/app/interfaces/gateway/gateway_runner.py`:

```python
"""Gateway runner — starts the channel gateway service.

This is the entry point for running Pythinker's multi-channel gateway.
It initializes nanobot's channel adapters and connects them to
Pythinker's AgentService via the MessageRouter bridge.

Usage:
    python -m app.interfaces.gateway.gateway_runner

Or via Docker Compose:
    docker compose --profile gateway up gateway
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

logger = logging.getLogger(__name__)


async def run_gateway() -> None:
    """Initialize and run the channel gateway."""
    from app.core.config import get_settings

    settings = get_settings()

    if not settings.channel_gateway_enabled:
        logger.error(
            "Channel gateway is disabled. Set CHANNEL_GATEWAY_ENABLED=true to enable."
        )
        sys.exit(1)

    # Lazy imports to avoid loading heavy deps when gateway is disabled
    from app.infrastructure.external.channels.nanobot_gateway import NanobotGateway
    from app.domain.services.channels.message_router import MessageRouter
    from app.infrastructure.repositories.user_channel_repository import (
        MongoUserChannelRepository,
    )

    # Initialize MongoDB connection (reuse Pythinker's motor client)
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_client = AsyncIOMotorClient(settings.mongodb_url)
    db = mongo_client[settings.mongodb_database]

    # Build the dependency chain
    user_repo = MongoUserChannelRepository(db)

    # AgentService requires more wiring — import from app factory
    from app.interfaces.dependencies import build_agent_service

    agent_service = await build_agent_service(settings, db)

    router = MessageRouter(
        agent_service=agent_service,
        user_channel_repo=user_repo,
    )

    gateway = NanobotGateway(
        message_router=router,
        telegram_token=settings.telegram_bot_token,
        telegram_allowed=settings.telegram_allowed_users,
        discord_token=settings.discord_bot_token,
        discord_allowed=settings.discord_allowed_users,
        slack_bot_token=settings.slack_bot_token,
        slack_app_token=settings.slack_app_token,
        slack_allowed=settings.slack_allowed_users,
    )

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_signal() -> None:
        logger.info("Received shutdown signal")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    # Start gateway
    await gateway.start()
    logger.info("Channel gateway is running. Press Ctrl+C to stop.")

    # Wait for shutdown signal
    await stop_event.wait()

    # Cleanup
    await gateway.stop()
    mongo_client.close()
    logger.info("Channel gateway stopped cleanly.")


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    asyncio.run(run_gateway())


if __name__ == "__main__":
    main()
```

**Step 2: Create MongoDB user channel repository**

Create `backend/app/infrastructure/repositories/user_channel_repository.py`:

```python
"""MongoDB repository for user-channel identity mapping."""

from __future__ import annotations

import uuid
import logging
from datetime import UTC, datetime
from typing import Any

from app.domain.models.channel import ChannelType

logger = logging.getLogger(__name__)


class MongoUserChannelRepository:
    """Stores user ↔ channel sender mappings in MongoDB."""

    def __init__(self, db: Any) -> None:
        self._links = db["user_channel_links"]
        self._sessions = db["channel_sessions"]

    async def get_user_by_channel(
        self, channel: ChannelType, sender_id: str
    ) -> str | None:
        """Find Pythinker user_id by channel sender."""
        doc = await self._links.find_one(
            {"channel": channel.value, "sender_id": sender_id}
        )
        return doc["user_id"] if doc else None

    async def create_channel_user(
        self, channel: ChannelType, sender_id: str, chat_id: str
    ) -> str:
        """Create a new auto-registered user for a channel sender."""
        user_id = f"channel-{uuid.uuid4().hex[:12]}"
        await self._links.insert_one({
            "user_id": user_id,
            "channel": channel.value,
            "sender_id": sender_id,
            "chat_id": chat_id,
            "linked_at": datetime.now(UTC),
        })
        logger.info("Created channel user %s for %s/%s", user_id, channel, sender_id)
        return user_id

    async def get_session_key(
        self, user_id: str, channel: ChannelType, chat_id: str
    ) -> str | None:
        """Get active session ID for this user+channel+chat."""
        doc = await self._sessions.find_one({
            "user_id": user_id,
            "channel": channel.value,
            "chat_id": chat_id,
        })
        if doc and doc.get("session_id"):
            return doc["session_id"]
        return None

    async def set_session_key(
        self, user_id: str, channel: ChannelType, chat_id: str, session_id: str
    ) -> None:
        """Store or clear the active session for this user+channel+chat."""
        await self._sessions.update_one(
            {"user_id": user_id, "channel": channel.value, "chat_id": chat_id},
            {"$set": {
                "session_id": session_id if session_id else None,
                "updated_at": datetime.now(UTC),
            }},
            upsert=True,
        )
```

**Step 3: Commit**

```bash
git add backend/app/interfaces/gateway/ \
        backend/app/infrastructure/repositories/user_channel_repository.py
git commit -m "feat(channels): add gateway runner and user channel repository

Gateway runner starts nanobot channels connected to Pythinker's agent.
MongoUserChannelRepository maps channel senders to Pythinker users."
```

---

## Task 8: Cron Integration — Bridge to Nanobot CronService

**Files:**
- Create: `backend/app/domain/services/tools/cron_tool.py`
- Create: `backend/app/infrastructure/services/cron_bridge.py`
- Test: `backend/tests/domain/services/tools/test_cron_tool.py`

**Step 1: Write failing test**

Create `backend/tests/domain/services/tools/test_cron_tool.py`:

```python
"""Tests for CronTool — agent can schedule/list/cancel cron jobs."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_cron_tool_schedule_task():
    from app.domain.services.tools.cron_tool import CronTool

    mock_cron = AsyncMock()
    mock_cron.add_job.return_value = "job-123"

    tool = CronTool(cron_service=mock_cron, user_id="user-1")
    result = await tool.execute(
        action="schedule",
        description="Generate daily report",
        cron_expr="0 9 * * *",
        timezone="UTC",
    )
    assert "job-123" in str(result.data) or "scheduled" in result.output.lower()
    mock_cron.add_job.assert_called_once()


@pytest.mark.asyncio
async def test_cron_tool_list_tasks():
    from app.domain.services.tools.cron_tool import CronTool

    mock_cron = AsyncMock()
    mock_cron.list_jobs.return_value = []

    tool = CronTool(cron_service=mock_cron, user_id="user-1")
    result = await tool.execute(action="list")
    assert result.output is not None


@pytest.mark.asyncio
async def test_cron_tool_cancel_task():
    from app.domain.services.tools.cron_tool import CronTool

    mock_cron = AsyncMock()
    mock_cron.remove_job.return_value = True

    tool = CronTool(cron_service=mock_cron, user_id="user-1")
    result = await tool.execute(action="cancel", job_id="job-123")
    mock_cron.remove_job.assert_called_once_with("job-123")
```

**Step 2: Run to verify failure**

```bash
cd backend && pytest tests/domain/services/tools/test_cron_tool.py -v
```

**Step 3: Implement CronTool**

Create `backend/app/domain/services/tools/cron_tool.py`:

```python
"""CronTool — allows the agent to schedule, list, and cancel recurring tasks."""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.models.tool_result import ToolResult


class CronServiceProtocol(Protocol):
    """Protocol for cron service (implemented by bridge to nanobot)."""

    async def add_job(
        self, user_id: str, description: str, cron_expr: str, timezone: str
    ) -> str: ...

    async def list_jobs(self, user_id: str) -> list[dict[str, Any]]: ...

    async def remove_job(self, job_id: str) -> bool: ...


class CronTool:
    """Agent tool for managing scheduled tasks.

    Bridges to nanobot's CronService via the CronServiceProtocol.
    """

    name = "schedule_task"
    description = (
        "Schedule, list, or cancel recurring tasks. "
        "Actions: 'schedule' (create new job), 'list' (show all jobs), "
        "'cancel' (remove a job by ID)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["schedule", "list", "cancel"],
                "description": "The action to perform",
            },
            "description": {
                "type": "string",
                "description": "Task description (for 'schedule' action)",
            },
            "cron_expr": {
                "type": "string",
                "description": "Cron expression, e.g. '0 9 * * *' for daily at 9 AM",
            },
            "timezone": {
                "type": "string",
                "description": "Timezone for the schedule, e.g. 'America/New_York'",
            },
            "job_id": {
                "type": "string",
                "description": "Job ID (for 'cancel' action)",
            },
        },
        "required": ["action"],
    }

    def __init__(self, cron_service: CronServiceProtocol, user_id: str) -> None:
        self._cron = cron_service
        self._user_id = user_id

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "list")

        if action == "schedule":
            desc = kwargs.get("description", "")
            expr = kwargs.get("cron_expr", "")
            tz = kwargs.get("timezone", "UTC")
            if not desc or not expr:
                return ToolResult(
                    tool_name=self.name,
                    output="Error: 'description' and 'cron_expr' are required for scheduling.",
                    data={},
                )
            job_id = await self._cron.add_job(self._user_id, desc, expr, tz)
            return ToolResult(
                tool_name=self.name,
                output=f"Task scheduled successfully. Job ID: {job_id}",
                data={"job_id": job_id, "status": "scheduled"},
            )

        elif action == "list":
            jobs = await self._cron.list_jobs(self._user_id)
            if not jobs:
                return ToolResult(
                    tool_name=self.name,
                    output="No scheduled tasks found.",
                    data={"jobs": []},
                )
            lines = [f"- {j.get('id', '?')}: {j.get('description', '?')} ({j.get('schedule', '?')})"
                     for j in jobs]
            return ToolResult(
                tool_name=self.name,
                output=f"Scheduled tasks:\n" + "\n".join(lines),
                data={"jobs": jobs},
            )

        elif action == "cancel":
            job_id = kwargs.get("job_id", "")
            if not job_id:
                return ToolResult(
                    tool_name=self.name,
                    output="Error: 'job_id' is required for cancel action.",
                    data={},
                )
            success = await self._cron.remove_job(job_id)
            status = "cancelled" if success else "not found"
            return ToolResult(
                tool_name=self.name,
                output=f"Job {job_id}: {status}",
                data={"job_id": job_id, "status": status},
            )

        return ToolResult(
            tool_name=self.name,
            output=f"Unknown action: {action}",
            data={},
        )
```

**Step 4: Create cron bridge to nanobot**

Create `backend/app/infrastructure/services/cron_bridge.py`:

```python
"""Bridge between Pythinker's CronTool and nanobot's CronService.

Wraps nanobot's file-based CronService, translating calls to/from
Pythinker's protocol. Nanobot CronService runs unmodified.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nanobot.cron.service import CronService as NanobotCronService

logger = logging.getLogger(__name__)


class CronBridge:
    """Bridges Pythinker CronTool protocol to nanobot's CronService."""

    def __init__(self, workspace_dir: str = "~/.pythinker/cron") -> None:
        store_path = Path(workspace_dir).expanduser()
        store_path.mkdir(parents=True, exist_ok=True)
        self._nanobot_cron = NanobotCronService(
            store_path=store_path / "jobs.json",
            on_job=self._handle_job,
        )

    async def start(self) -> None:
        """Start the cron scheduler."""
        await self._nanobot_cron.start()
        logger.info("CronBridge started")

    def stop(self) -> None:
        """Stop the cron scheduler."""
        self._nanobot_cron.stop()

    async def add_job(
        self, user_id: str, description: str, cron_expr: str, timezone: str
    ) -> str:
        """Schedule a new cron job."""
        job = self._nanobot_cron.add_job(
            name=f"{user_id}:{description[:50]}",
            schedule=None,
            message=description,
            cron_expr=cron_expr,
            tz=timezone,
        )
        return job.id if hasattr(job, "id") else str(job)

    async def list_jobs(self, user_id: str) -> list[dict[str, Any]]:
        """List all jobs for a user."""
        all_jobs = self._nanobot_cron.list_jobs(include_disabled=False)
        return [
            {
                "id": j.id,
                "description": j.payload.message if j.payload else "",
                "schedule": str(j.schedule),
                "enabled": j.enabled,
                "next_run": str(j.next_run_at) if j.next_run_at else None,
            }
            for j in all_jobs
            if j.name.startswith(f"{user_id}:")
        ]

    async def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID."""
        try:
            self._nanobot_cron.remove_job(job_id)
            return True
        except (KeyError, ValueError):
            return False

    async def _handle_job(self, job: Any) -> str | None:
        """Handle a triggered cron job — delegates to AgentService."""
        # This callback is invoked by nanobot's CronService when a job fires.
        # The gateway_runner will wire this to create an agent session.
        logger.info("Cron job triggered: %s", job.name if hasattr(job, "name") else job)
        return None  # Will be wired in gateway_runner
```

**Step 5: Run tests**

```bash
cd backend && pytest tests/domain/services/tools/test_cron_tool.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/domain/services/tools/cron_tool.py \
        backend/app/infrastructure/services/cron_bridge.py \
        backend/tests/domain/services/tools/test_cron_tool.py
git commit -m "feat(cron): add CronTool and CronBridge to nanobot

CronTool lets agents schedule/list/cancel tasks. CronBridge wraps
nanobot's CronService without modifying it."
```

---

## Task 9: Subagent Spawning — SpawnTool Bridge

**Files:**
- Create: `backend/app/domain/services/tools/spawn_tool.py`
- Test: `backend/tests/domain/services/tools/test_spawn_tool.py`

**Step 1: Write failing test**

Create `backend/tests/domain/services/tools/test_spawn_tool.py`:

```python
"""Tests for SpawnTool — agent spawns background subtasks."""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_spawn_tool_creates_background_task():
    from app.domain.services.tools.spawn_tool import SpawnTool

    mock_manager = AsyncMock()
    mock_manager.spawn.return_value = "task-abc123"
    mock_manager.get_running_count.return_value = 0

    tool = SpawnTool(subagent_manager=mock_manager, max_concurrent=3)
    result = await tool.execute(
        task="Research latest GPU benchmarks",
        label="gpu-research",
    )
    assert "task-abc123" in str(result.data)
    mock_manager.spawn.assert_called_once()


@pytest.mark.asyncio
async def test_spawn_tool_rejects_when_at_limit():
    from app.domain.services.tools.spawn_tool import SpawnTool

    mock_manager = AsyncMock()
    mock_manager.get_running_count.return_value = 3

    tool = SpawnTool(subagent_manager=mock_manager, max_concurrent=3)
    result = await tool.execute(task="Another task")
    assert "limit" in result.output.lower() or "maximum" in result.output.lower()
```

**Step 2: Run to verify failure**

```bash
cd backend && pytest tests/domain/services/tools/test_spawn_tool.py -v
```

**Step 3: Implement SpawnTool**

Create `backend/app/domain/services/tools/spawn_tool.py`:

```python
"""SpawnTool — allows the agent to spawn background subtasks.

Wraps nanobot's SubagentManager to run parallel background tasks
within a Pythinker session.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.models.tool_result import ToolResult


class SubagentManagerProtocol(Protocol):
    """Protocol for subagent manager."""

    async def spawn(self, task: str, label: str | None = None, **kwargs: Any) -> str: ...
    def get_running_count(self) -> int: ...


class SpawnTool:
    """Agent tool for spawning background subtasks."""

    name = "spawn_background_task"
    description = (
        "Spawn a background task that runs independently and reports results "
        "when complete. Useful for parallel research or long-running operations."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Description of the task for the background agent",
            },
            "label": {
                "type": "string",
                "description": "Optional short label for tracking the task",
            },
        },
        "required": ["task"],
    }

    def __init__(
        self,
        subagent_manager: SubagentManagerProtocol,
        max_concurrent: int = 3,
    ) -> None:
        self._manager = subagent_manager
        self._max_concurrent = max_concurrent

    async def execute(self, **kwargs: Any) -> ToolResult:
        task = kwargs.get("task", "")
        label = kwargs.get("label")

        if not task:
            return ToolResult(
                tool_name=self.name,
                output="Error: 'task' description is required.",
                data={},
            )

        # Check concurrency limit
        running = self._manager.get_running_count()
        if running >= self._max_concurrent:
            return ToolResult(
                tool_name=self.name,
                output=f"Maximum concurrent tasks limit reached ({self._max_concurrent}). "
                       f"Wait for a running task to complete.",
                data={"running": running, "limit": self._max_concurrent},
            )

        task_id = await self._manager.spawn(task=task, label=label)
        return ToolResult(
            tool_name=self.name,
            output=f"Background task spawned: {label or task_id}. "
                   f"Results will be reported when complete.",
            data={"task_id": task_id, "label": label, "status": "spawned"},
        )
```

**Step 4: Run tests**

```bash
cd backend && pytest tests/domain/services/tools/test_spawn_tool.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/spawn_tool.py \
        backend/tests/domain/services/tools/test_spawn_tool.py
git commit -m "feat(subagent): add SpawnTool for background task execution

Agent can spawn parallel background subtasks with concurrency limits.
Bridges to nanobot's SubagentManager via protocol."
```

---

## Task 10: Skills System — Bridge to Nanobot SkillLoader

**Files:**
- Create: `backend/app/domain/services/tools/skill_tools.py`
- Test: `backend/tests/domain/services/tools/test_skill_tools.py`

**Step 1: Write failing test**

Create `backend/tests/domain/services/tools/test_skill_tools.py`:

```python
"""Tests for skill tools — read, list, create skills."""
import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_list_skills():
    from app.domain.services.tools.skill_tools import ListSkillsTool

    mock_loader = MagicMock()
    mock_loader.list_skills.return_value = [
        {"name": "weather", "description": "Get weather info"},
        {"name": "github", "description": "Git operations"},
    ]

    tool = ListSkillsTool(skill_loader=mock_loader)
    result = await tool.execute()
    assert "weather" in result.output
    assert "github" in result.output


@pytest.mark.asyncio
async def test_read_skill():
    from app.domain.services.tools.skill_tools import ReadSkillTool

    mock_loader = MagicMock()
    mock_loader.load_skill.return_value = "# Weather Skill\nUse the weather API..."

    tool = ReadSkillTool(skill_loader=mock_loader)
    result = await tool.execute(skill_name="weather")
    assert "Weather Skill" in result.output
```

**Step 2: Run to verify failure**

```bash
cd backend && pytest tests/domain/services/tools/test_skill_tools.py -v
```

**Step 3: Implement skill tools**

Create `backend/app/domain/services/tools/skill_tools.py`:

```python
"""Skill tools — allow the agent to discover and use markdown-based skills.

Bridges to nanobot's SkillsLoader which handles skill discovery,
metadata parsing, and progressive loading.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.models.tool_result import ToolResult


class SkillLoaderProtocol(Protocol):
    """Protocol for skill loading (backed by nanobot's SkillsLoader)."""

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, Any]]: ...
    def load_skill(self, name: str) -> str | None: ...


class ListSkillsTool:
    """List available agent skills."""

    name = "list_skills"
    description = "List all available skills with their descriptions."
    parameters = {"type": "object", "properties": {}}

    def __init__(self, skill_loader: SkillLoaderProtocol) -> None:
        self._loader = skill_loader

    async def execute(self, **kwargs: Any) -> ToolResult:
        skills = self._loader.list_skills()
        if not skills:
            return ToolResult(
                tool_name=self.name,
                output="No skills available.",
                data={"skills": []},
            )
        lines = [f"- **{s['name']}**: {s.get('description', 'No description')}"
                 for s in skills]
        return ToolResult(
            tool_name=self.name,
            output="Available skills:\n" + "\n".join(lines),
            data={"skills": skills},
        )


class ReadSkillTool:
    """Read the full content of a specific skill."""

    name = "read_skill"
    description = "Read the full instructions of a skill by name."
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Name of the skill to read",
            },
        },
        "required": ["skill_name"],
    }

    def __init__(self, skill_loader: SkillLoaderProtocol) -> None:
        self._loader = skill_loader

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs.get("skill_name", "")
        if not name:
            return ToolResult(
                tool_name=self.name,
                output="Error: 'skill_name' is required.",
                data={},
            )
        content = self._loader.load_skill(name)
        if content is None:
            return ToolResult(
                tool_name=self.name,
                output=f"Skill '{name}' not found.",
                data={},
            )
        return ToolResult(
            tool_name=self.name,
            output=content,
            data={"skill_name": name},
        )
```

**Step 4: Run tests**

```bash
cd backend && pytest tests/domain/services/tools/test_skill_tools.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/tools/skill_tools.py \
        backend/tests/domain/services/tools/test_skill_tools.py
git commit -m "feat(skills): add ListSkillsTool and ReadSkillTool

Agent can discover and read markdown-based skills via nanobot's
SkillsLoader. Progressive loading keeps context window small."
```

---

## Task 11: Wire Everything in Composition Root

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/domain/services/tools/dynamic_toolset.py`

**Step 1: Add new tool category to dynamic_toolset.py**

In `backend/app/domain/services/tools/dynamic_toolset.py`, add to `ToolCategory` enum:

```python
AUTOMATION = "automation"  # Cron, subagent, skills tools
```

Add to `TASK_PATTERNS`:

```python
"automation": [r"schedule", r"cron", r"recurring", r"automate", r"daily", r"weekly"],
"delegation": [r"background", r"parallel", r"spawn", r"subtask", r"delegate"],
"skills": [r"skill", r"template", r"recipe", r"how.to"],
```

**Step 2: Wire new tools in agent_task_runner.py**

In the flow initialization section of `agent_task_runner.py` (where scraper, deal_finder are wired), add:

```python
# ── Cron Tool ────────────────────────────────
_cron_tool = None
if settings.cron_service_enabled:
    try:
        from app.infrastructure.services.cron_bridge import CronBridge
        from app.domain.services.tools.cron_tool import CronTool
        _cron_bridge = CronBridge()
        _cron_tool = CronTool(cron_service=_cron_bridge, user_id=self._user_id)
    except Exception as exc:
        logger.warning("CronTool unavailable: %s", exc)

# ── Spawn Tool ───────────────────────────────
_spawn_tool = None
if settings.subagent_spawning_enabled:
    try:
        from app.domain.services.tools.spawn_tool import SpawnTool
        from nanobot.agent.subagent import SubagentManager
        # SubagentManager needs a provider — reuse Pythinker's LLM
        _spawn_tool = SpawnTool(
            subagent_manager=SubagentManager(...),  # Wire with LLM provider
            max_concurrent=settings.subagent_max_concurrent,
        )
    except Exception as exc:
        logger.warning("SpawnTool unavailable: %s", exc)

# ── Skill Tools ──────────────────────────────
_skill_tools = []
if settings.skills_system_enabled:
    try:
        from nanobot.agent.skills import SkillsLoader
        from app.domain.services.tools.skill_tools import ListSkillsTool, ReadSkillTool
        from pathlib import Path
        _skill_loader = SkillsLoader(
            workspace=Path(settings.skills_workspace_dir).expanduser()
        )
        _skill_tools = [
            ListSkillsTool(skill_loader=_skill_loader),
            ReadSkillTool(skill_loader=_skill_loader),
        ]
    except Exception as exc:
        logger.warning("SkillTools unavailable: %s", exc)
```

**Step 3: Run full test suite**

```bash
cd backend && pytest tests/ -x --ignore=tests/nanobot -q 2>&1 | tail -20
```

Expected: All existing tests pass (new tools only load when feature-flagged on).

**Step 4: Commit**

```bash
git add backend/app/domain/services/agent_task_runner.py \
        backend/app/domain/services/tools/dynamic_toolset.py
git commit -m "feat(integration): wire cron, spawn, and skill tools in composition root

New tools are feature-flagged and only loaded when enabled. Added
AUTOMATION tool category for cron/spawn/skill task patterns."
```

---

## Task 12: Docker Compose — Gateway Service

**Files:**
- Modify: `docker-compose.yml` (add gateway service with profile)

**Step 1: Add gateway service**

Add to `docker-compose.yml` (after the backend service):

```yaml
  gateway:
    image: ${IMAGE_REGISTRY:-pythinker}/pythinker-backend:${IMAGE_TAG:-latest}
    platform: linux/amd64
    build:
      context: ./backend
      dockerfile: Dockerfile
    profiles:
      - gateway  # Only starts with: docker compose --profile gateway up
    depends_on:
      backend:
        condition: service_healthy
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    command: ["python", "-m", "app.interfaces.gateway.gateway_runner"]
    env_file:
      - .env
    environment:
      - CHANNEL_GATEWAY_ENABLED=true
    networks:
      - pythinker-network
```

**Step 2: Test that gateway starts (manual)**

```bash
# Set up env vars first
export CHANNEL_GATEWAY_ENABLED=true
export TELEGRAM_BOT_TOKEN=test  # Replace with real token for actual test

# Test with Docker
docker compose --profile gateway up gateway
```

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(gateway): add channel gateway Docker Compose service

Runs as separate profile: docker compose --profile gateway up gateway.
Reuses backend image with different entry point."
```

---

## Task 13: Integration Tests

**Files:**
- Create: `backend/tests/integration/test_channel_integration.py`

**Step 1: Write integration test**

Create `backend/tests/integration/test_channel_integration.py`:

```python
"""Integration tests for channel gateway pipeline.

These tests verify the full flow:
InboundMessage → MessageRouter → AgentService → OutboundMessage

Requires: MongoDB (uses test database)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.channel import ChannelType, InboundMessage
from app.domain.services.channels.message_router import MessageRouter


@pytest.mark.asyncio
async def test_full_channel_pipeline_greeting():
    """A simple greeting through the channel pipeline returns a response."""
    mock_agent = AsyncMock()
    mock_session = MagicMock(id="test-sess")
    mock_agent.create_session.return_value = mock_session

    # Simulate agent returning a message event
    class FakeEvent:
        type = "message"
        content = "Hello! How can I help you?"

    mock_agent.send_message.return_value = [FakeEvent()].__iter__()

    mock_repo = AsyncMock()
    mock_repo.get_user_by_channel.return_value = "test-user"
    mock_repo.get_session_key.return_value = None

    router = MessageRouter(agent_service=mock_agent, user_channel_repo=mock_repo)

    msg = InboundMessage(
        channel=ChannelType.TELEGRAM,
        sender_id="tg-test",
        chat_id="tg-chat",
        content="Hello",
    )

    responses = []
    async for out in router.route_inbound(msg):
        responses.append(out)

    assert len(responses) >= 1
    assert "Hello" in responses[0].content or "help" in responses[0].content.lower()
    assert responses[0].channel == ChannelType.TELEGRAM
    assert responses[0].chat_id == "tg-chat"


@pytest.mark.asyncio
async def test_nanobot_imports_available():
    """Verify all nanobot imports are accessible."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.base import BaseChannel
    from nanobot.channels.manager import ChannelManager
    from nanobot.cron.service import CronService
    from nanobot.agent.skills import SkillsLoader
    from nanobot.agent.subagent import SubagentManager

    assert AgentLoop is not None
    assert MessageBus is not None
    assert BaseChannel is not None
    assert ChannelManager is not None
    assert CronService is not None
    assert SkillsLoader is not None
    assert SubagentManager is not None
```

**Step 2: Run integration tests**

```bash
cd backend && pytest tests/integration/test_channel_integration.py -v
```

Expected: PASS

**Step 3: Run full regression suite**

```bash
cd backend && pytest tests/ -x --ignore=tests/nanobot -q
```

Expected: All pass.

**Step 4: Commit**

```bash
git add backend/tests/integration/test_channel_integration.py
git commit -m "test(channels): add channel pipeline integration tests

Verifies full InboundMessage → MessageRouter → AgentService flow
and confirms all nanobot imports are accessible."
```

---

## Task 14: Final Lint & Documentation

**Step 1: Run linters**

```bash
cd backend && ruff check . && ruff format --check .
```

Fix any issues.

**Step 2: Run full test suite one last time**

```bash
cd backend && pytest tests/ -x -q
```

Expected: All pass.

**Step 3: Commit any fixes**

```bash
git add -u && git commit -m "style: fix lint issues from nanobot integration"
```

---

## Summary: What Gets Created

| # | File | Purpose | Phase |
|---|------|---------|-------|
| 1 | `backend/nanobot/` | Vendored nanobot package (as-is) | Task 1 |
| 2 | `backend/tests/nanobot/` | Nanobot's own tests | Task 1 |
| 3 | `backend/app/core/config_channels.py` | Channel/cron/skills settings | Task 2 |
| 4 | `backend/app/domain/models/channel.py` | Channel message models | Task 3 |
| 5 | `backend/app/domain/models/scheduled_job.py` | Cron job model | Task 3 |
| 6 | `backend/app/domain/external/channel_gateway.py` | Gateway protocol | Task 4 |
| 7 | `backend/app/domain/services/channels/message_router.py` | Bridge service | Task 5 |
| 8 | `backend/app/infrastructure/external/channels/nanobot_gateway.py` | Nanobot adapter | Task 6 |
| 9 | `backend/app/infrastructure/repositories/user_channel_repository.py` | User mapping | Task 7 |
| 10 | `backend/app/interfaces/gateway/gateway_runner.py` | Startup entry | Task 7 |
| 11 | `backend/app/domain/services/tools/cron_tool.py` | Cron agent tool | Task 8 |
| 12 | `backend/app/infrastructure/services/cron_bridge.py` | Cron → nanobot | Task 8 |
| 13 | `backend/app/domain/services/tools/spawn_tool.py` | Subagent tool | Task 9 |
| 14 | `backend/app/domain/services/tools/skill_tools.py` | Skill tools | Task 10 |

**Files modified:** `config.py`, `session.py`, `agent_task_runner.py`, `dynamic_toolset.py`, `requirements.txt`, `docker-compose.yml`, `.env.example`

**Nanobot code changes:** ZERO — all nanobot code copied as-is.

**Feature flags (all default False):**
- `CHANNEL_GATEWAY_ENABLED` — master switch
- `CRON_SERVICE_ENABLED` — cron scheduling
- `HEARTBEAT_ENABLED` — periodic wake-up
- `SKILLS_SYSTEM_ENABLED` — markdown skills
- `SUBAGENT_SPAWNING_ENABLED` — background tasks
