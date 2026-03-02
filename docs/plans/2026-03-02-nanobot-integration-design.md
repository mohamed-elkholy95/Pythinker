# Nanobot Full Merge Integration Design

**Date**: 2026-03-02
**Status**: Approved
**Approach**: Port & Adapt — merge nanobot's best features into Pythinker's DDD architecture

## Goal

Merge nanobot (~4,000 lines) into Pythinker (~39K lines) as native capabilities:
1. **Multi-channel chat gateway** — Telegram, Discord (Phase 1), Slack, WhatsApp, Email (Phase 5)
2. **Cron scheduling + Heartbeat** — scheduled agent tasks with periodic wake-ups
3. **Markdown skills system** — progressive skill loading for agent capabilities
4. **Subagent spawning** — background task execution within sessions

**Design principle**: One brain, many mouths. All channels feed into the same `AgentService.send_message()` pipeline. The domain layer has zero knowledge of channel specifics.

---

## Architecture

```
                    ┌──────────────────────────────────┐
                    │         Pythinker Core            │
                    │  (PlanActFlow / CoordinatorFlow)  │
                    │  (Tools, Memory, Sandbox, LLM)    │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │      Channel Gateway Service      │
                    │   (MessageBus + ChannelManager)   │
                    └──┬──────┬──────┬──────┬──────┬──┘
                       │      │      │      │      │
                    ┌──▼─┐ ┌─▼──┐ ┌▼───┐ ┌▼───┐ ┌▼──┐
                    │ TG │ │ DC │ │Slk │ │ WA │ │Web│
                    │Bot │ │Bot │ │Bot │ │Bot │ │ UI│
                    └────┘ └────┘ └────┘ └────┘ └───┘
```

### New DDD Layers

```
domain/
  external/
    channel.py              # Channel Protocol (ABC)
  models/
    channel.py              # InboundMessage, OutboundMessage, ChannelType, UserChannelLink
    scheduled_job.py        # ScheduledJob model
  services/
    channels/
      channel_manager.py    # Manages channel lifecycle (start/stop)
      message_router.py     # Routes inbound → AgentService → outbound
      event_formatter.py    # Base event → channel-specific formatting
    skills/
      skill_loader.py       # Discovers and loads SKILL.md files
      builtin/              # Bundled skills (ported from nanobot)
    agents/
      subagent_manager.py   # Background subagent lifecycle

infrastructure/
  external/
    channels/
      base.py               # BaseChannelAdapter (shared ACL, retry, metrics)
      telegram.py           # TelegramChannelAdapter (python-telegram-bot)
      discord.py            # DiscordChannelAdapter (discord.py)
  services/
    cron_service.py         # Cron job scheduler (croniter + asyncio)
    heartbeat_service.py    # Periodic background task runner
  repositories/
    scheduled_job_repository.py  # MongoDB persistence for cron jobs
    user_channel_repository.py   # user ↔ channel sender mapping

interfaces/
  api/
    channel_routes.py       # Webhook endpoints (Telegram webhook mode)
  gateway/
    gateway_runner.py       # CLI entry: starts MessageBus + channels
```

---

## Feature 1: Channel Gateway

### Message Flow (Inbound)

```
User sends message on Telegram
    ↓
TelegramAdapter receives update (polling or webhook)
    ↓
Validates sender via allowFrom ACL
    ↓
Creates InboundMessage(channel=TELEGRAM, sender_id="123", chat_id="456", content="...")
    ↓
MessageBus.publish_inbound(message)
    ↓
MessageRouter consumes from bus:
    1. Maps sender_id → Pythinker user_id (via user_channel_links in MongoDB)
    2. Gets or creates Session (mode=AGENT, source=TELEGRAM)
    3. Calls AgentService.send_message(session_id, user_id, content)
    4. Iterates BaseEvent stream
    ↓
EventFormatter converts events for Telegram:
    - PlanEvent → "📋 Planning: 3 steps..."
    - ToolEvent → "🔧 Searching web..."
    - ReportEvent → Markdown (split if >4096 chars)
    - DoneEvent → (no output)
    ↓
OutboundMessage → TelegramAdapter.send() → Telegram API
```

### Domain Models

```python
class ChannelType(StrEnum):
    WEB = "web"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    EMAIL = "email"

class InboundMessage(BaseModel):
    channel: ChannelType
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime
    media: list[MediaAttachment] = []
    metadata: dict[str, Any] = {}
    session_key_override: str | None = None  # For threads

class OutboundMessage(BaseModel):
    channel: ChannelType
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[MediaAttachment] = []
    metadata: dict[str, Any] = {}

class UserChannelLink(BaseModel):
    user_id: str
    channel: ChannelType
    sender_id: str
    chat_id: str
    display_name: str | None = None
    linked_at: datetime
```

### Channel Protocol (Domain)

```python
class Channel(Protocol):
    channel_type: ChannelType

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> None: ...
    def is_allowed(self, sender_id: str) -> bool: ...
```

### Event Formatting

Each channel gets a `EventFormatter` that converts Pythinker domain events:

| Event | Telegram | Discord | Web UI |
|-------|----------|---------|--------|
| PlanEvent | Summary + step list | Embed with fields | Full JSON via SSE |
| ToolEvent | Inline status edit | Thread update | Real-time SSE |
| ReportEvent | Chunked markdown | Embed or thread | Full render |
| ProgressEvent | Edit previous msg | Edit embed | SSE update |
| ErrorEvent | Error message | Red embed | Error SSE |

### Session Management

- **Session key**: `{channel_type}:{chat_id}` — one session per chat
- **User mapping**: `user_channel_links` MongoDB collection
- **Auto-linking**: First message from unknown sender creates pending link; user must `/link <code>` from web UI to confirm (security)
- **Slash commands**: `/new` (fresh session), `/stop` (cancel), `/help`, `/status`

### Configuration

```python
class ChannelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    # Global
    channel_gateway_enabled: bool = False
    channel_message_bus_size: int = 1000

    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_users: list[str] = []
    telegram_webhook_mode: bool = False
    telegram_webhook_url: str = ""
    telegram_proxy_url: str = ""

    # Discord
    discord_bot_token: str = ""
    discord_allowed_users: list[str] = []
    discord_guild_ids: list[str] = []
```

---

## Feature 2: Cron Scheduling & Heartbeat

### Cron Service

**Storage**: MongoDB `scheduled_jobs` collection

```python
class ScheduledJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    schedule_type: Literal["cron", "interval", "once"]
    schedule_expr: str          # "0 9 * * *" or "30m" or ISO datetime
    task_description: str       # What the agent should do
    channel: ChannelType | None = None  # Delivery channel (None = web UI)
    chat_id: str | None = None
    timezone: str = "UTC"
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    max_runs: int | None = None  # None = unlimited
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Execution flow**:
1. CronService.tick() checks next_run for all enabled jobs
2. When a job fires: creates Session(mode=AGENT, source=CRON)
3. Calls `AgentService.send_message(session_id, user_id, task_description)`
4. Streams results to configured channel (or stores for web UI)
5. Updates last_run, next_run, run_count

**Agent tool** (`CronTool`):
- `schedule_task(description, cron_expr, timezone)` → creates job
- `list_scheduled_tasks()` → user's jobs
- `cancel_scheduled_task(job_id)` → disables

### Heartbeat Service

- Interval: configurable (default 30 min)
- Reads `HEARTBEAT.md` from user workspace
- LLM decides: skip or execute each checklist item
- Results delivered to user's preferred channel
- Feature flag: `heartbeat_enabled: bool = False`

---

## Feature 3: Skills System

### Skill Format

```yaml
---
description: "Generate Plotly charts from data"
metadata: '{"pythinker": {"always": false, "tools": ["code_executor"], "requires": {"env": ["PLOTLY_AVAILABLE"]}}}'
---

# Chart Generation Skill

When the user asks to create a chart or visualization...
[Full skill instructions]
```

### Skill Discovery

1. **Builtin**: `backend/app/domain/services/skills/builtin/*.md`
2. **Workspace**: User-configured skill directory (default: `~/.pythinker/skills/`)
3. **always: true** skills → injected into system prompt automatically
4. **Other skills** → listed in summary; agent reads via `read_skill` tool

### Agent Tools

- `read_skill(skill_name)` → returns full skill content
- `list_skills()` → available skills with descriptions
- `create_skill(name, description, content)` → saves to workspace

### Integration with Existing Prompts

Skills extend `ContextBuilder` (from nanobot's pattern):
- System prompt includes: identity + memory + always-skills + skill-summary
- No change to existing prompt system — skills are additive

---

## Feature 4: Subagent Spawning

### SpawnTool

Registered in Pythinker's dynamic toolset:

```python
class SpawnTool(BaseTool):
    name = "spawn_background_task"
    description = "Spawn a background task that runs independently"

    async def execute(self, task: str, label: str | None = None) -> ToolResult:
        task_id = await self.subagent_manager.spawn(
            task=task,
            label=label,
            session_id=self.session_id,
            user_id=self.user_id,
        )
        return ToolResult(data={"task_id": task_id, "status": "spawned"})
```

### SubagentManager

- Tracks active background tasks per session
- Each subagent runs a lightweight `FastPathFlow` (no planning overhead)
- Limited tool access: no spawn tool (prevents recursion), no browser (resource-heavy)
- Results delivered as `MessageEvent` to parent session
- `/stop` cancels all subagents for session
- Max concurrent subagents per session: 3 (configurable)

---

## Configuration Summary

```bash
# Channel Gateway
CHANNEL_GATEWAY_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USERS=123456,789012
DISCORD_BOT_TOKEN=
DISCORD_ALLOWED_USERS=
DISCORD_GUILD_IDS=

# Cron
CRON_SERVICE_ENABLED=false
HEARTBEAT_ENABLED=false
HEARTBEAT_INTERVAL_MINUTES=30

# Skills
SKILLS_SYSTEM_ENABLED=false
SKILLS_WORKSPACE_DIR=~/.pythinker/skills

# Subagents
SUBAGENT_SPAWNING_ENABLED=false
SUBAGENT_MAX_CONCURRENT=3
SUBAGENT_MAX_ITERATIONS=15
```

All features are **off by default** (feature-flagged). Zero impact on existing deployments.

---

## Implementation Phases

### Phase 1: Channel Infrastructure (Foundation)
- Domain protocols and models
- MessageBus (asyncio.Queue-based)
- MessageRouter (inbound → AgentService → outbound)
- ChannelManager (lifecycle)
- EventFormatter base class
- Configuration (config_channels.py)
- MongoDB: user_channel_links collection
- Gateway runner entry point
- Unit tests

### Phase 2: Telegram + Discord Adapters
- TelegramChannelAdapter (python-telegram-bot)
- DiscordChannelAdapter (discord.py or raw gateway)
- EventFormatter implementations per channel
- Slash commands (/new, /stop, /help)
- User identity linking
- Message chunking for platform limits
- Media support (images, files)
- Docker Compose: gateway service
- Integration tests

### Phase 3: Cron & Heartbeat
- ScheduledJob model + MongoDB repository
- CronService with croniter
- CronTool (agent tool)
- HeartbeatService
- Configuration + feature flags
- Unit + integration tests

### Phase 4: Skills & Subagents
- SkillLoader service
- Builtin skills (port from nanobot)
- Skill agent tools (read, list, create)
- System prompt integration
- SpawnTool + SubagentManager
- Cancellation and lifecycle management
- Unit tests

### Phase 5: Polish & Expansion
- Additional channel adapters (Slack, WhatsApp, Email)
- Vue admin dashboard (channels, jobs, skills)
- Cross-channel session continuity
- Comprehensive test coverage
- Architecture documentation

---

## Dependencies to Add

```
# requirements.txt additions
python-telegram-bot[socks]>=22.0   # Telegram channel
discord.py>=2.5.0                  # Discord channel (or raw websocket)
croniter>=6.0.0                    # Cron expression parsing
```

Note: `croniter` and `python-telegram-bot` are already dependencies of nanobot and well-tested.

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Channel adapter crashes | Circuit breaker + auto-restart per channel |
| Message bus overflow | Bounded queue (1000) + backpressure |
| LLM cost from scheduled tasks | Per-user daily budget limit on cron jobs |
| Subagent infinite loops | Max iterations (15) + max concurrent (3) |
| Security (unauthorized access) | ACL per channel + user linking confirmation |
| Session state corruption | Channel messages use same AgentService path as web UI |

---

## Files to Create (Estimated)

| File | Lines (est.) | Phase |
|------|-------------|-------|
| `domain/external/channel.py` | ~40 | 1 |
| `domain/models/channel.py` | ~80 | 1 |
| `domain/models/scheduled_job.py` | ~50 | 3 |
| `domain/services/channels/channel_manager.py` | ~120 | 1 |
| `domain/services/channels/message_router.py` | ~200 | 1 |
| `domain/services/channels/event_formatter.py` | ~100 | 1 |
| `domain/services/skills/skill_loader.py` | ~150 | 4 |
| `domain/services/agents/subagent_manager.py` | ~180 | 4 |
| `infrastructure/external/channels/base.py` | ~100 | 1 |
| `infrastructure/external/channels/telegram.py` | ~250 | 2 |
| `infrastructure/external/channels/discord.py` | ~250 | 2 |
| `infrastructure/services/cron_service.py` | ~200 | 3 |
| `infrastructure/services/heartbeat_service.py` | ~100 | 3 |
| `infrastructure/repositories/scheduled_job_repository.py` | ~80 | 3 |
| `infrastructure/repositories/user_channel_repository.py` | ~60 | 1 |
| `core/config_channels.py` | ~60 | 1 |
| `core/config_cron.py` | ~30 | 3 |
| `interfaces/gateway/gateway_runner.py` | ~100 | 1 |
| `domain/services/tools/cron_tool.py` | ~80 | 3 |
| `domain/services/tools/spawn_tool.py` | ~60 | 4 |
| `domain/services/tools/skill_tools.py` | ~80 | 4 |
| Tests (per phase) | ~200 each | 1-5 |
| **Total** | **~3,200** | |

---

## Success Criteria

1. User can message Pythinker via Telegram and receive full agent responses
2. User can message Pythinker via Discord and receive full agent responses
3. Agent can schedule recurring tasks via CronTool
4. Agent can load and use markdown skills
5. Agent can spawn background subagents for parallel work
6. All features are feature-flagged and off by default
7. Zero regression on existing tests (4762+)
8. All new code follows Pythinker's DDD conventions
