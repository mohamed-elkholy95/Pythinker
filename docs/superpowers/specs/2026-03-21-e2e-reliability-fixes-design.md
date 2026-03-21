# E2E Reliability — Full Architecture Refactor

**Date**: 2026-03-21
**Status**: Approved
**Approach**: C — Full Architecture Refactor (safe: pre-launch, zero users)
**Scope**: Redesign 3 core systems + fix 6 E2E issues
**Validation**: Context7 MCP — FastAPI (`/websites/fastapi_tiangolo`, 83.79), Vue.js (`/websites/vuejs`, 67.9), Pydantic (`/websites/pydantic_dev`, 85.81)

---

## Why Full Refactor (Not Incremental Patches)

The E2E test revealed 6 issues, but the root causes point to **3 architectural debts**:

1. **`plan_act.py` is 4,250 lines** — a god class that owns streaming, cancellation, tool dispatch, plan management, phase transitions, and error recovery. No amount of patching fixes the structural problem.

2. **Conversation context captures 5 of 42 event types** (88% data loss) — the extraction function was designed for a simpler event model and never expanded. The system literally forgets plans, thoughts, verifications, reflections, and mode changes.

3. **Intent classifier is session-blind** — it classifies messages in isolation without considering what the session has done. A follow-up to a research task gets the same treatment as a fresh greeting.

Since we have **zero production users**, refactoring the critical path carries no deployment risk. The incremental approach (Approach B) would leave the 4,250-line god class intact.

---

## Problem Statement

| ID | Severity | Issue | Architectural Root Cause |
|----|----------|-------|--------------------------|
| 1 | **P0** | Session cancelled after 84s | Tool execution not shielded; no cancellation grace period |
| 2 | **P0** | Follow-up hallucinates wrong topic | 88% event data loss + session-blind classifier |
| 3 | **P1** | "Task completed" shown for cancelled | No distinct UI state for interrupted sessions |
| 4 | **P1** | Resume cursor format mismatch | Frontend stores UUID, backend expects Redis stream ID |
| 5 | **P1** | Sandbox context not ready at startup | Insufficient retry with linear backoff |
| 6 | **P2** | Suggestions not accessible | `<div>` without ARIA attributes |

---

## Refactor Scope

### System 1: Streaming & Tool Execution Pipeline

**Current**: `plan_act.py` (4,250 lines) — monolithic flow owning everything

**Refactored into**:

| New Module | Responsibility | Est. Lines |
|-----------|----------------|------------|
| `plan_act.py` | Orchestration only — phase state machine, event routing | ~800 |
| `stream_executor.py` (NEW) | Streaming loop with idle timeout, heartbeat interleaving, cancellation grace | ~250 |
| `tool_executor.py` (NEW) | Shielded tool dispatch with progress heartbeats | ~200 |
| `cancellation.py` (ENHANCED) | Grace period support, reconnection-aware token | ~50 added |

### System 2: Conversation Context Service

**Current**: `conversation_context_service.py` (658 lines) — captures 5 of 42 event types

**Refactored**:

| Change | Detail |
|--------|--------|
| `extract_turn_from_event()` | Expanded from 5 to 12 event types (all context-bearing events) |
| `TurnEventType` enum | 5 → 12 values |
| `TurnRole` enum | 4 → 6 values (add PLAN_SUMMARY, THOUGHT) |
| New: priority ranking | Events ranked by context value for retrieval scoring |

### System 3: Intent Classifier

**Current**: `intent_classifier.py` (483 lines) — session-blind

**Refactored**:

| Change | Detail |
|--------|--------|
| `ClassificationContext` | Add `session_had_plan`, `session_mode`, `prior_topic` fields |
| `classify_with_context()` | Session-aware guards prevent mode downgrade during active plans |
| New: `SessionContextExtractor` | Extracts plan/topic summary from session events for classifier |

---

## Phase 1: Stream Executor Extraction

**Goal**: Extract the streaming loop from `plan_act.py` into a reusable, tested component with built-in cancellation grace and tool heartbeats.

### 1.1 New: `stream_executor.py`

**File**: `backend/app/domain/services/flows/stream_executor.py`

Extracts the streaming loop currently at `plan_act.py:2042-2108` into a dedicated class:

```python
"""Streaming executor with cancellation grace and heartbeat interleaving.

Wraps an inner async generator (the actual workflow) and adds:
- Wall-clock timeout (max_execution_time_seconds)
- Idle timeout that resets on every yielded event
- Cancellation grace period during tool execution
- Heartbeat interleaving during long-running operations
"""

class StreamExecutor:
    """Execute an async event generator with timeout and cancellation management."""

    def __init__(
        self,
        cancel_token: CancellationToken,
        session_id: str,
        agent_id: str,
        wall_clock_timeout: int,      # from settings.max_execution_time_seconds
        idle_timeout: int,            # from settings.effective_workflow_idle_timeout
        grace_period: int = 5,        # seconds to wait before cancelling during tools
    ) -> None: ...

    async def execute(
        self,
        inner: AsyncGenerator[BaseEvent, None],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Stream events from inner generator with timeout and cancellation management.

        The key improvement over the previous inline loop:
        1. Tool-active state tracked via ToolEvent start/complete
        2. During tool execution, cancellation check uses grace period
        3. Heartbeats interleaved automatically for long gaps
        """
        try:
            async with asyncio.timeout(self._wall_clock_timeout):
                inner_iter = inner.__aiter__()
                tool_active = False

                while True:
                    # Cancellation check with grace period awareness
                    await self._check_cancelled(tool_active=tool_active)

                    try:
                        async with asyncio.timeout(self._idle_timeout):
                            event = await inner_iter.__anext__()
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        yield self._build_idle_timeout_error()
                        yield DoneEvent()
                        return

                    # Track tool execution state for grace period
                    if isinstance(event, ToolEvent):
                        if event.status == ToolStatus.CALLING:
                            tool_active = True
                        elif event.status == ToolStatus.CALLED:
                            tool_active = False

                    yield event

        except asyncio.CancelledError:
            logger.info("StreamExecutor: workflow cancelled for %s", self._session_id)
            raise
        except TimeoutError:
            yield self._build_wall_clock_error()
            yield DoneEvent()

    async def _check_cancelled(self, tool_active: bool = False) -> None:
        """Check cancellation with grace period during tool execution."""
        if not self._cancel_token.is_cancelled():
            return
        if tool_active and self._grace_period > 0:
            # Wait for potential SSE reconnection before cancelling
            await asyncio.sleep(self._grace_period)
            if not self._cancel_token.is_cancelled():
                return  # Client reconnected
        raise asyncio.CancelledError(f"Session {self._session_id} cancelled")
```

**Integration in `plan_act.py`**: The `run()` method (currently lines 2042-2108) becomes:

```python
async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
    executor = StreamExecutor(
        cancel_token=self._cancel_token,
        session_id=self._session_id,
        agent_id=self._agent_id,
        wall_clock_timeout=settings.max_execution_time_seconds,
        idle_timeout=settings.effective_workflow_idle_timeout,
        grace_period=settings.cancellation_grace_period_seconds,
    )
    async for event in executor.execute(self._run_with_trace(message)):
        yield event
```

This replaces ~70 lines of inline timeout/cancellation logic with a 3-line delegation.

### 1.2 New: `tool_executor.py`

**File**: `backend/app/domain/services/flows/tool_executor.py`

Wraps individual tool calls with heartbeat emission:

```python
"""Shielded tool execution with progress heartbeats.

Uses the existing LLMHeartbeat + interleave_heartbeat pattern
(from llm_heartbeat.py) to emit ProgressEvent(phase=TOOL_EXECUTING)
every 5 seconds during tool execution, keeping the idle timeout alive.
"""

class ToolExecutorWithHeartbeat:
    """Execute tool calls with heartbeat emission for long-running operations."""

    def __init__(self, interval_seconds: float = 5.0) -> None:
        self._interval = interval_seconds

    async def execute(
        self,
        tool_call: ToolCall,
        execute_fn: Callable[..., Awaitable[Any]],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute a tool call, yielding heartbeats during execution."""
        heartbeat = LLMHeartbeat(
            phase=PlanningPhase.TOOL_EXECUTING,
            message=f"Running {tool_call.name}...",
            interval_seconds=self._interval,
        )

        async def _tool_gen() -> AsyncGenerator[BaseEvent, None]:
            result = await execute_fn(tool_call)
            yield result

        async with heartbeat:
            async for event in interleave_heartbeat(_tool_gen(), heartbeat):
                yield event
```

### 1.3 `PlanningPhase` Enum Addition

**File**: `backend/app/domain/models/event.py` (lines 577-587)

Add the missing phase:

```python
class PlanningPhase(str, Enum):
    RECEIVED = "received"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    FINALIZING = "finalizing"
    HEARTBEAT = "heartbeat"
    WAITING = "waiting"
    VERIFYING = "verifying"
    EXECUTING_SETUP = "executing_setup"
    TOOL_EXECUTING = "tool_executing"  # NEW: Active tool execution heartbeat
```

### 1.4 `CancellationToken` Enhancement

**File**: `backend/app/domain/utils/cancellation.py`

Add reconnection-awareness to the existing token. The SSE route layer must clear the
disconnect event when a new SSE connection attaches to the same session:

```python
# Add to CancellationToken:
def clear(self) -> None:
    """Clear cancellation state (e.g., when client reconnects)."""
    if self._event is not None:
        self._event.clear()
        self._checked_count = 0
```

**In `session_routes.py`**: When a new SSE connection opens for an already-running session,
call `disconnect_event.clear()` to signal reconnection.

### 1.5 Config Addition

**File**: `backend/app/core/config_features.py`

```python
cancellation_grace_period_seconds: int = 5
```

### 1.6 Status Contradiction Fix (Frontend)

**File**: `frontend/src/pages/ChatPage.vue`

Add distinct interrupted state:

```typescript
const isSessionInterrupted = computed(() =>
  sessionStatus.value === SessionStatus.CANCELLED &&
  hasReceivedPartialOutput.value
)
```

**New component**: `frontend/src/components/report/TaskInterruptedFooter.vue`

Amber-styled footer with "Task was interrupted" text and "Retry" button that resubmits
the original message with attachments (stored in session events).

**Files touched** (Phase 1):
- `stream_executor.py` (NEW, ~250 lines)
- `tool_executor.py` (NEW, ~100 lines)
- `plan_act.py` (REDUCE: extract ~200 lines of streaming/timeout logic)
- `event.py` (add `TOOL_EXECUTING` to `PlanningPhase`)
- `cancellation.py` (add `clear()` method)
- `config_features.py` (add grace period setting)
- `session_routes.py` (clear disconnect event on reconnection)
- `ChatPage.vue` (add interrupted state)
- `TaskInterruptedFooter.vue` (NEW component)

---

## Phase 2: Conversation Context Service Redesign

**Goal**: Capture all context-bearing events (not just 5 of 42), with priority ranking for retrieval quality.

### 2.1 Expanded Event Extraction

**File**: `backend/app/domain/services/conversation_context_service.py` (method `extract_turn_from_event`)

Redesign the extraction to handle 12 event types organized by context value:

```python
# Priority tiers for retrieval scoring
# Tier 1 (highest): Direct user/assistant content
# Tier 2: Execution artifacts (plans, tools, steps)
# Tier 3: Meta-context (thoughts, reflections, verifications)

EVENT_EXTRACTION_MAP: dict[type, tuple[TurnRole, TurnEventType, int]] = {
    # Tier 1: Primary content (priority weight 1.0)
    MessageEvent:    (TurnRole.dynamic,     TurnEventType.MESSAGE,         100),
    ReportEvent:     (TurnRole.ASSISTANT,    TurnEventType.REPORT,          100),

    # Tier 2: Execution artifacts (priority weight 0.8)
    PlanEvent:       (TurnRole.PLAN_SUMMARY, TurnEventType.PLAN,            80),
    ToolEvent:       (TurnRole.TOOL_SUMMARY, TurnEventType.TOOL_RESULT,     80),
    StepEvent:       (TurnRole.STEP_SUMMARY, TurnEventType.STEP_COMPLETION, 80),

    # Tier 3: Meta-context (priority weight 0.6)
    ThoughtEvent:    (TurnRole.THOUGHT,      TurnEventType.THOUGHT,         60),
    ReflectionEvent: (TurnRole.ASSISTANT,     TurnEventType.REFLECTION,      60),
    VerificationEvent: (TurnRole.ASSISTANT,   TurnEventType.VERIFICATION,    60),
    ErrorEvent:      (TurnRole.ASSISTANT,     TurnEventType.ERROR,           60),

    # Tier 4: Structural (priority weight 0.4)
    ComprehensionEvent: (TurnRole.ASSISTANT,  TurnEventType.COMPREHENSION,   40),
    ModeChangeEvent:    (TurnRole.ASSISTANT,  TurnEventType.MODE_CHANGE,     40),
    TaskRecreationEvent: (TurnRole.ASSISTANT, TurnEventType.TASK_RECREATION, 40),
}
```

**Content extraction per event type**:

```python
def _extract_content(self, event: BaseEvent) -> str | None:
    """Extract storable content from any supported event type."""
    match event:
        case MessageEvent():
            return event.message
        case ReportEvent():
            title = event.title or ""
            return f"{title}\n{event.content or ''}"[:2000]
        case PlanEvent() if event.status == PlanStatus.CREATED:
            steps = "\n".join(f"- {s.description}" for s in (event.plan.steps or []))
            return f"Plan: {event.plan.title or 'Untitled'}\nSteps:\n{steps}"
        case PlanEvent():
            return None  # Skip UPDATED/COMPLETED (only store initial plan)
        case ToolEvent() if event.status == ToolStatus.CALLED:
            name = event.tool_name or event.function_name or "unknown"
            result = str(event.function_result or "")[:500]
            return f"{name}: {result}"
        case ToolEvent():
            return None  # Skip CALLING status
        case StepEvent() if event.status == StepStatus.COMPLETED:
            desc = event.step.description if event.step else ""
            result = str(getattr(event.step, "result", "") or "")[:500]
            return f"Step: {desc}. Result: {result}"
        case StepEvent():
            return None  # Skip non-completed
        case ThoughtEvent() if event.is_final:
            return f"Thought ({event.thought_type}): {event.content}"
        case ThoughtEvent():
            return None  # Skip non-final thoughts
        case ReflectionEvent():
            return f"Reflection: {event.summary or event.decision}"
        case VerificationEvent():
            return f"Verification ({event.status}): {event.summary}"
        case ErrorEvent() if event.error:
            return f"Error: {event.error}"
        case ComprehensionEvent():
            return f"Task comprehension: {event.summary}"
        case ModeChangeEvent():
            return f"Mode changed to {event.mode}: {event.reason}"
        case TaskRecreationEvent():
            return f"Task recreated: {event.reason}"
        case _:
            return None
```

### 2.2 Expanded Enums

**File**: `backend/app/domain/models/conversation_context.py`

```python
class TurnRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_SUMMARY = "tool_summary"
    STEP_SUMMARY = "step_summary"
    PLAN_SUMMARY = "plan_summary"     # NEW
    THOUGHT = "thought"               # NEW

class TurnEventType(StrEnum):
    MESSAGE = "message"
    TOOL_RESULT = "tool_result"
    STEP_COMPLETION = "step_completion"
    REPORT = "report"
    ERROR = "error"
    PLAN = "plan"                     # NEW
    THOUGHT = "thought"               # NEW
    REFLECTION = "reflection"         # NEW
    VERIFICATION = "verification"     # NEW
    COMPREHENSION = "comprehension"   # NEW
    MODE_CHANGE = "mode_change"       # NEW
    TASK_RECREATION = "task_recreation" # NEW
```

### 2.3 Priority-Weighted Retrieval

Enhance the semantic retrieval to boost higher-priority turns:

```python
# In _retrieve_context_impl(), after hybrid search:
# Apply priority weighting from EVENT_EXTRACTION_MAP
for result in semantic_results:
    priority = EVENT_EXTRACTION_MAP.get(
        type(result.source_event), (None, None, 50)
    )[2]
    result.relevance_score *= (priority / 100.0)
```

This ensures PlanEvents and MessageEvents rank higher than ThoughtEvents in retrieval.

**Files touched** (Phase 2):
- `conversation_context_service.py` (REWRITE extraction: ~150 lines replaced)
- `conversation_context.py` (expand enums: ~20 lines added)

---

## Phase 3: Session-Aware Intent Classifier

**Goal**: Make the classifier respect session execution history — never downgrade a planned session to discuss mode without high confidence.

### 3.1 Enhanced `ClassificationContext`

**File**: `backend/app/domain/services/agents/intent_classifier.py`

Add session execution history to the classification context:

```python
@dataclass
class ClassificationContext:
    # Existing fields
    attachments: list[dict[str, Any]]
    available_skills: list[str]
    conversation_length: int
    is_follow_up: bool
    urls: list[str]
    mcp_tools: list[str]

    # NEW: Session execution awareness
    session_mode: AgentMode | None = None        # Current session mode
    session_had_plan: bool = False                # Session created a plan
    session_plan_title: str | None = None         # Plan topic for context
    session_status: SessionStatus | None = None   # Current session status
    session_completed_steps: int = 0              # How many steps completed
```

### 3.2 Session-Aware Classification Guards

Add guards in `classify_with_context()` that prevent harmful mode switches:

```python
def classify_with_context(
    self, message: str, context: ClassificationContext | None = None
) -> ClassificationResult:
    # Base classification (existing logic)
    intent, mode, confidence = self.classify(message)
    reasons = [f"Base classification: {intent} ({confidence:.2f})"]

    if context is None:
        return ClassificationResult(intent, mode, confidence, reasons, {})

    # === NEW: Session-aware guards ===

    # Guard 1: Never downgrade AGENT→DISCUSS if session had a plan
    if (
        context.session_mode == AgentMode.AGENT
        and mode == AgentMode.DISCUSS
        and context.session_had_plan
    ):
        reasons.append(
            f"BLOCKED: AGENT→DISCUSS downgrade prevented — "
            f"session has plan '{context.session_plan_title}'"
        )
        return ClassificationResult(
            intent="follow_up_to_planned_task",
            mode=AgentMode.AGENT,
            confidence=0.90,
            reasons=reasons,
            context_signals={"plan_guard_active": True},
        )

    # Guard 2: Follow-up with continuation phrases in planned session
    if (
        context.is_follow_up
        and context.session_had_plan
        and self._is_continuation_phrase(message)
    ):
        reasons.append("Continuation phrase in planned session → AGENT")
        return ClassificationResult(
            intent="continuation",
            mode=AgentMode.AGENT,
            confidence=0.95,
            reasons=reasons,
            context_signals={"continuation_in_plan": True},
        )

    # ... existing context-aware logic (attachments, URLs, skills) ...
```

### 3.3 New: `SessionContextExtractor`

**File**: `backend/app/domain/services/agents/session_context_extractor.py` (NEW)

Extracts plan/topic summary from session events for the classifier and discuss prompt:

```python
"""Extract session execution context for intent classification and prompt injection.

Provides a lightweight summary of what a session has done — plans created,
steps completed, topics researched — without requiring full event replay.
"""

class SessionContextExtractor:
    """Extract execution context from a session's event history."""

    @staticmethod
    def extract(session: Session) -> SessionExecutionContext:
        """Build a summary of the session's execution history."""
        from app.domain.models.event import PlanEvent, StepEvent, PlanStatus, StepStatus

        plan_title: str | None = None
        plan_steps: list[str] = []
        completed_steps: int = 0
        had_plan = False

        for event in (session.events or []):
            if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                had_plan = True
                plan_title = event.plan.title
                plan_steps = [s.description for s in (event.plan.steps or [])]
            elif isinstance(event, StepEvent) and event.status == StepStatus.COMPLETED:
                completed_steps += 1

        return SessionExecutionContext(
            had_plan=had_plan,
            plan_title=plan_title,
            plan_steps=plan_steps,
            completed_steps=completed_steps,
            topic=plan_title or session.title,
        )

@dataclass
class SessionExecutionContext:
    had_plan: bool
    plan_title: str | None
    plan_steps: list[str]
    completed_steps: int
    topic: str | None

    def to_plan_summary(self) -> str:
        """Format as text for prompt injection."""
        if not self.had_plan:
            return ""
        steps = "\n".join(f"  - {s}" for s in self.plan_steps)
        progress = f" ({self.completed_steps}/{len(self.plan_steps)} completed)"
        return f"Plan: {self.plan_title}{progress}\nSteps:\n{steps}"
```

### 3.4 Wire Into `agent_task_factory.py`

**File**: `backend/app/domain/services/agents/agent_task_factory.py` (lines 399-443)

```python
async def classify_intent_with_context(self, message, session, ...):
    # Extract session execution context
    from app.domain.services.agents.session_context_extractor import (
        SessionContextExtractor,
    )
    exec_ctx = SessionContextExtractor.extract(session)

    context = ClassificationContext(
        # ... existing fields ...
        session_mode=session.mode,
        session_had_plan=exec_ctx.had_plan,
        session_plan_title=exec_ctx.plan_title,
        session_status=session.status,
        session_completed_steps=exec_ctx.completed_steps,
    )
    result = classifier.classify_with_context(message, context)
    # ... existing mode change logic ...
```

### 3.5 Inject Plan Context Into Discuss Prompt

**File**: `backend/app/domain/services/prompts/discuss.py`

When building the discuss prompt for a follow-up in a session that had a plan:

```python
def build_discuss_prompt(
    message: str,
    attachments: str = "",
    language: str = "English",
    context: str = "",
    plan_summary: str = "",  # NEW: from SessionContextExtractor
) -> str:
    context_block = ""
    if context:
        context_block = f"<retrieved_context>\n{context}\n</retrieved_context>\n\n"
    plan_block = ""
    if plan_summary:
        plan_block = (
            "<prior_task_context>\n"
            "The user previously asked you to work on a task. Here is the plan:\n"
            f"{plan_summary}\n"
            "Answer follow-up questions in the context of this prior task.\n"
            "</prior_task_context>\n\n"
        )
    return DISCUSS_PROMPT.format(
        message=message,
        attachments=attachments or "None",
        language=language,
        context_block=context_block + plan_block,
    )
```

**Files touched** (Phase 3):
- `intent_classifier.py` (add session guards: ~60 lines)
- `session_context_extractor.py` (NEW: ~80 lines)
- `agent_task_factory.py` (wire extractor: ~15 lines)
- `discuss.py` (add plan_summary param: ~15 lines)

---

## Phase 4: Event Resume, Startup, & Frontend Polish

### 4.1 Fix Resume Cursor Format (Frontend-Only Fix)

**Root cause**: `client.ts` stores the JSON payload's `event_id` (UUID) as `lastReceivedEventId`
instead of the SSE `id:` field (Redis stream format). The backend already only emits Redis-format
IDs as the SSE `id:` field.

**File**: `frontend/src/api/client.ts`

```typescript
// Fix: Use SSE id: field (Redis stream format "1234567890-0")
// instead of payload event_id (UUID format "e70a6c37-...")
if (sseEvent.id) {
    lastReceivedEventId = sseEvent.id;
}
// Remove the line that sets from payload UUID
```

### 4.2 Fix Sandbox Context Startup Race

**File**: `backend/app/domain/services/prompts/sandbox_context.py`

```python
_RETRY_ATTEMPTS = 6        # was 3
_RETRY_BASE_DELAY = 1.0    # was 2.0

# Exponential backoff: 1s, 2s, 4s, 8s, 16s (5 sleeps for 6 attempts) = ~31s
delay = cls._RETRY_BASE_DELAY * (2 ** attempt)
```

**File**: `backend/app/core/lifespan.py`

Add tracked background task for deferred sandbox context loading:

```python
# Store task reference for shutdown cancellation (existing pattern in lifespan.py)
sandbox_reload_task = asyncio.create_task(_reload_sandbox_context_on_ready())
# Cancel in shutdown block: sandbox_reload_task.cancel()
```

### 4.3 Suggestions Accessibility (Context7 Validated: Vue.js WAI-ARIA)

**File**: `frontend/src/components/Suggestions.vue` (lines 6-10)

```html
<div
  v-for="(suggestion, index) in suggestions"
  :key="index"
  class="suggestion-item"
  role="button"
  tabindex="0"
  :aria-label="suggestion"
  @click="$emit('select', suggestion)"
  @keydown.enter="$emit('select', suggestion)"
  @keydown.space.prevent="$emit('select', suggestion)"
>
```

### 4.4 Topic-Aware Follow-Up Suggestions

Use plan title/session title in suggestion templates instead of skill name:

```python
topic = plan.title or session.title or "this topic"
suggestions = [
    f"Can you expand on {topic} with an example?",
    f"What are the best next steps for {topic}?",
    f"What trade-offs should I consider for {topic}?",
]
```

### 4.5 Dependency Version Pinning

**File**: `backend/requirements.txt`

```
urllib3>=2.0,<2.6
charset-normalizer>=3.0,<3.4
```

### 4.6 Stale Session Cleanup

**File**: `backend/app/application/services/maintenance_service.py`

Add to periodic cleanup: sessions with `title=None`, `status=cancelled`,
`latest_message=None`, `age > 24 hours`.

**Files touched** (Phase 4):
- `client.ts` (~5 lines)
- `sandbox_context.py` (~10 lines)
- `lifespan.py` (~15 lines)
- `Suggestions.vue` (~5 lines)
- Suggestion generator backend (~10 lines)
- `requirements.txt` (~2 lines)
- `maintenance_service.py` (~15 lines)

---

## Deployment Sequence

```
Phase 1 (Stream Executor)  ──→  Phase 2 (Context Service)  ──→  Phase 3 (Intent Classifier)  ──→  Phase 4 (Polish)
        │                              │                              │                              │
   Extract streaming loop         Expand event capture           Add session guards            Frontend + cleanup
   Add tool heartbeats            12 event types                 SessionContextExtractor       Accessibility
   Cancellation grace             Priority-weighted retrieval    Plan context injection        Resume cursor fix
   Interrupted UI state                                                                        Sandbox startup
```

Each phase is independently testable. Phase 1 and 2 should land together for maximum impact.

---

## Testing Strategy

| Phase | Unit Tests | Integration Tests | E2E Tests |
|-------|-----------|-------------------|-----------|
| 1 | `StreamExecutor`: idle timeout, grace period, tool state tracking; `ToolExecutorWithHeartbeat`: heartbeat emission at 5s intervals | SSE disconnect during tool exec → verify grace period delays cancellation; reconnect within grace → verify resumption | Full research task runs to completion |
| 2 | `extract_turn_from_event`: all 12 event types; priority weighting; content extraction for each match case | Record PlanEvent → retrieve in follow-up → verify plan appears in context | Follow-up question returns topic-relevant answer |
| 3 | `SessionContextExtractor`: plan detection, step counting; classifier guards: AGENT→DISCUSS blocked when plan exists | Follow-up to research session → mode stays AGENT; fresh greeting → mode is DISCUSS | Research → follow-up → verify no hallucination |
| 4 | Suggestions keyboard navigation; cursor format validation | SSE reconnect with correct cursor format | Accessibility audit (axe-core) |

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `plan_act.py` extraction breaks existing flow | Medium | High | Keep `_run_with_trace()` intact; only extract the outer streaming loop |
| 12 event types increase Qdrant write volume | Low | Low | Tier 3-4 events are filtered by content length (50 char min) |
| Session guard too aggressive (never reaches discuss) | Medium | Medium | Guard only fires when `session_had_plan=True`; fresh sessions unaffected |
| `match/case` syntax requires Python 3.10+ | None | None | Project already uses Python 3.12 |
| Grace period delays legitimate user cancellation | Low | Low | User-initiated "Stop" button sets a separate flag that bypasses grace |
| Retry with attachments loses context | Low | Medium | Store original message + attachments in session events |

## Total Scope Summary

| Phase | New Files | Modified Files | New Lines | Modified Lines |
|-------|-----------|---------------|-----------|----------------|
| 1 | 3 (`stream_executor.py`, `tool_executor.py`, `TaskInterruptedFooter.vue`) | 6 | ~600 | ~250 |
| 2 | 0 | 2 | ~170 | ~150 |
| 3 | 1 (`session_context_extractor.py`) | 3 | ~80 | ~90 |
| 4 | 0 | 7 | ~60 | ~30 |
| **Total** | **4 new files** | **18 modified files** | **~910 lines** | **~520 lines** |

Net effect: `plan_act.py` shrinks by ~200 lines. Conversation context captures 12 event types
instead of 5. Intent classifier gains session awareness. All 6 E2E issues resolved.
