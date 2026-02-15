# Plan: Apply PicoClaw Design Patterns to Pythinker Agent

## Context

PicoClaw is an ultra-lightweight Go agent with excellent organizational patterns that Pythinker lacks. After a thorough gap analysis, Pythinker already **exceeds** PicoClaw in safety/guardrails (39 security patterns, input/output guardrails, hallucination detection, circuit breakers). However, Pythinker is missing 4 organizational patterns that would make it more capable and self-maintaining.

**What we're adding (4 gaps):**

| # | Feature | Priority | New Lines | Files |
|---|---------|----------|-----------|-------|
| 1 | LLM-Based Session Summarization | P0 | ~250 | 1 new, 1 modified |
| 2 | Heartbeat/Cron Periodic Tasks | P0 | ~350 | 1 new, 2 modified |
| 3 | True Async Subagent Spawning | P1 | ~200 | 1 new, 1 modified |
| 4 | Three-Tier Skills Resolver | P1 | ~200 | 1 new, 1 modified |

**Total: 4 new files, 4 modified files, ~1,000 lines**

---

## PicoClaw Review Summary

### What PicoClaw Does Well
- **Agent Loop**: Iterative tool-calling with max 20 iterations, context building from workspace files (AGENT.md, SOUL.md, IDENTITY.md)
- **Guardrails**: Multi-layer safety — workspace sandboxing, dangerous command regex blocking (rm -rf, fork bombs, dd, shutdown), 60s timeouts, 10K char output truncation
- **Tools**: Interface-based registry, async tools with callbacks, subagent spawning (fire-and-forget)
- **Skills**: 3-tier loading (builtin → global → workspace) via Markdown SKILL.md files
- **Sessions**: Auto-summarization when >20 messages or >75% context window (LLM-driven)
- **Architecture**: Message bus decoupling channels from agent, heartbeat/cron for periodic tasks, atomic state persistence

### Pythinker vs PicoClaw Comparison

| Feature | Pythinker | PicoClaw | Status |
|---------|-----------|----------|--------|
| Max iteration limits | 400 iterations + weighted budgeting | Basic 20 limit | **PYTHINKER BETTER** |
| Dangerous command blocking | 39 patterns + LLM review | 8 regex patterns | **PYTHINKER BETTER** |
| Output truncation | Category-specific (2k-50k chars) | 10k flat limit | **PYTHINKER BETTER** |
| Input guardrails | 16 injection patterns, PII detection | None | **PYTHINKER BETTER** |
| Hallucination detection | Tool call validation, CoVe | None | **PYTHINKER BETTER** |
| Session management | Token compaction (loses context) | LLM summarization (preserves context) | **PICOCLAW BETTER** |
| Periodic tasks | None | Heartbeat + cron service | **PICOCLAW BETTER** |
| Subagent spawning | Synchronous only | Async fire-and-forget | **PICOCLAW BETTER** |
| Skills architecture | Flat tool structure | 3-tier precedence | **PICOCLAW BETTER** |

---

## Gap 1: LLM-Based Session Summarization (P0)

**Problem:** `_ensure_within_token_limit()` at `base.py:1395` only trims/compacts — semantic context is lost. PicoClaw uses LLM to summarize before truncating, preserving key facts and decisions.

**Solution:** New `SessionSummarizer` service called before compaction.

### New File: `backend/app/domain/services/agents/session_summarizer.py` (~250 lines)

```python
class SessionSummary(TypedDict):
    key_facts: list[str]       # Critical facts from conversation
    decisions_made: list[str]  # Decisions and their reasoning
    current_task: str          # What agent is currently doing
    tools_used: list[str]      # Tools used and outcomes

class SessionSummarizer:
    def __init__(self, llm: LLM, token_manager: TokenManager):
        ...

    async def should_summarize(self, messages: list[Message]) -> bool:
        """Trigger: >20 messages OR >75% token window."""

    async def summarize(self, messages: list[Message], keep_recent: int = 4) -> list[Message]:
        """LLM-summarize old messages, return [summary_msg] + recent messages."""
        # 1. Split: old_messages = messages[:-4], recent = messages[-4:]
        # 2. LLM call with structured summarization prompt
        # 3. Return [system_summary_message] + recent
```

### Modified: `backend/app/domain/services/agents/base.py`
- In `_ensure_within_token_limit()` (~line 1395): Call `SessionSummarizer.should_summarize()` first. If true, summarize before trimming.
- Add `_session_summarizer` attribute initialized in `__init__`

### Config: `backend/app/core/config.py`
```python
session_summarization_enabled: bool = True
session_summary_message_threshold: int = 20
session_summary_token_ratio: float = 0.75
```

### Metric: `pythinker_session_summaries_total{trigger=messages|tokens}`

---

## Gap 2: Heartbeat/Cron Periodic Tasks (P0)

**Problem:** No periodic task execution. PicoClaw runs health checks, memory consolidation, cleanup automatically via heartbeat service.

**Solution:** Async `HeartbeatService` running in FastAPI lifespan.

### New File: `backend/app/domain/services/agents/heartbeat_service.py` (~350 lines)

```python
class HeartbeatTaskType(StrEnum):
    HEALTH_CHECK = "health_check"           # Sandbox/service health
    SESSION_CLEANUP = "session_cleanup"     # Stale session cleanup
    MEMORY_CONSOLIDATION = "memory_consolidation"  # Merge short-term → long-term memory
    METRIC_SNAPSHOT = "metric_snapshot"     # Log key metrics

class HeartbeatTask(TypedDict):
    type: HeartbeatTaskType
    interval_seconds: int
    last_run: datetime | None
    enabled: bool

class HeartbeatService:
    def __init__(self, settings: Settings):
        self._tasks: list[HeartbeatTask] = [...]
        self._running = False

    async def start(self) -> None:
        """Start background loop. Called from FastAPI lifespan."""
        self._running = True
        asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False

    async def _run_loop(self) -> None:
        """Tick every 10s, check which tasks are due, execute them."""

    async def _execute_health_check(self) -> None:
        """Check sandbox containers, Redis, MongoDB connectivity."""

    async def _execute_session_cleanup(self) -> None:
        """Remove sessions idle >24h (configurable)."""

    async def _execute_memory_consolidation(self) -> None:
        """Merge user short-term memories into long-term via Qdrant."""
```

### Modified: `backend/app/interfaces/api/main.py`
- In FastAPI lifespan: `heartbeat = HeartbeatService(settings); await heartbeat.start()` on startup, `await heartbeat.stop()` on shutdown.

### Config: `backend/app/core/config.py`
```python
heartbeat_enabled: bool = True
heartbeat_health_check_interval: int = 60      # seconds
heartbeat_session_cleanup_interval: int = 3600  # 1 hour
heartbeat_memory_consolidation_interval: int = 1800  # 30 min
heartbeat_stale_session_hours: int = 24
```

### Metric: `pythinker_heartbeat_executions_total{task_type}`, `pythinker_heartbeat_duration_seconds{task_type}`

---

## Gap 3: True Async Subagent Spawning (P1)

**Problem:** `AgentSpawner` at `spawner.py` is synchronous — blocks parent agent. PicoClaw fires-and-forgets via goroutines with callback notification.

**Solution:** Add `spawn_async()` method using existing Redis job queue infrastructure (`backend/app/infrastructure/queue/redis_job_queue.py`).

### New File: `backend/app/infrastructure/workers/subagent_worker.py` (~200 lines)

```python
class SubagentWorker:
    """Processes async subagent jobs from Redis queue."""

    def __init__(self, job_queue: RedisJobQueue, agent_factory, settings: Settings):
        ...

    async def start(self) -> None:
        """Start consuming from 'subagent' queue."""

    async def process_job(self, job: Job) -> None:
        """Create agent, execute task, publish completion event via SSE."""

    async def stop(self) -> None:
        """Graceful shutdown."""
```

### Modified: `backend/app/domain/services/agents/spawner.py`
- Add `async def spawn_async(self, config: SpawnedAgentConfig) -> str:` method
- Enqueues job to Redis queue, returns job_id immediately
- Parent agent gets non-blocking `ToolResult(content="Subagent spawned, job_id=...")`

### Config: `backend/app/core/config.py`
```python
subagent_worker_enabled: bool = True
subagent_max_concurrent: int = 3
subagent_default_timeout: int = 300
```

### Metric: `pythinker_async_subagent_total{status=started|completed|failed}`

---

## Gap 4: Three-Tier Skills Resolver (P1)

**Problem:** Flat tool structure with 40+ tools. PicoClaw has workspace → global → builtin skill precedence with SKILL.md files providing rich context.

**Solution:** `SkillResolver` that organizes tools into discoverable skill groups with precedence.

### New File: `backend/app/domain/services/tools/skill_resolver.py` (~200 lines)

```python
class SkillTier(StrEnum):
    WORKSPACE = "workspace"  # Project-specific (from sandbox /workspace/skills/)
    USER = "user"            # User custom skills (from MongoDB)
    BUILTIN = "builtin"      # Core tools (search, browser, file, shell, etc.)

class SkillDefinition(TypedDict):
    name: str
    description: str
    tier: SkillTier
    tools: list[str]          # Tool names in this skill
    instructions: str         # Markdown instructions (like SKILL.md)

class SkillResolver:
    def __init__(self, tool_registry: dict[str, BaseTool]):
        ...

    async def resolve(self, sandbox_id: str | None = None) -> list[SkillDefinition]:
        """Load skills in precedence order: workspace → user → builtin.
        Higher tiers override lower tiers with same name."""

    def get_builtin_skills(self) -> list[SkillDefinition]:
        """Group existing 40+ tools into ~8 logical skill categories."""
        # research: info_search_web, info_search_academic, info_fetch_url
        # browser: browser_navigate, browser_click, browser_input, browser_agent
        # files: file_read, file_write, file_search, file_list_directory
        # shell: shell_execute
        # code: code_execute, code_list_artifacts, code_read_artifact
        # memory: memory_store, memory_search
        # communication: message_user, ask_user
        # mcp: mcp_* tools

    async def load_workspace_skills(self, sandbox_id: str) -> list[SkillDefinition]:
        """Read SKILL.md files from /workspace/skills/ in sandbox."""

    def load_user_skills(self, user_id: str) -> list[SkillDefinition]:
        """Load user-created skills from DB (existing skill creator)."""
```

### Modified: `backend/app/domain/services/agents/base.py`
- In context building: Include resolved skill descriptions in system prompt
- Skills provide additional context/instructions beyond just tool definitions

### Config: `backend/app/core/config.py`
```python
skill_resolution_enabled: bool = True
```

---

## Implementation Order

1. **Gap 1** (Session Summarization) — standalone, immediate value, no infrastructure deps
2. **Gap 2** (Heartbeat Service) — standalone, requires FastAPI lifespan integration
3. **Gap 3** (Async Subagents) — builds on existing Redis job queue
4. **Gap 4** (Skills Resolver) — organizational improvement, lowest risk

## Verification

1. **Gap 1**: Run agent with >20 messages, verify summary is generated and context preserved
2. **Gap 2**: Start server, check logs for heartbeat ticks, verify health check runs
3. **Gap 3**: Trigger subagent spawn, verify parent doesn't block, verify SSE completion event
4. **Gap 4**: Check skill resolution in agent system prompt, verify workspace skills load from sandbox

**Tests**: One test file per gap in `backend/tests/domain/services/agents/`

**Lint/Format**: `ruff check . && ruff format --check .` after each gap
