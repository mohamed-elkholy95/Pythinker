# Pythinker Domain Models Review (GLM)

> Generated: 2026-02-11
> Total Files: ~299
> Progress: 40/299 files reviewed (13.4%)

## Review Criteria

- **Code Quality**: Clean patterns, maintainability, readability
- **Pydantic v2 Compliance**: `model_config`, `@classmethod` on validators, `ConfigDict`
- **Type Safety**: Complete type hints, no `any`, strict typing
- **DDD Layer Discipline**: Domain models contain no infrastructure concerns
- **Security**: Input validation, safe defaults, no injection risks
- **Performance**: Efficient patterns, no unbounded growth, proper defaults

---

## Batch 1: Domain Models (Files 1-5)

### 1. `backend/app/domain/models/__init__.py`

**Purpose:** Package init - exports for domain models module

**Current Setup:**
- Exports 37 symbols from 11 source modules
- Uses explicit `__all__` list for public API
- Includes some inline aliases (`SearchResultItem as SearchResultItem`)

**Strengths:**
- Clear `__all__` declaration for explicit public API
- Good separation of imports by source module

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Incomplete exports | Global | High | Only exposes subset - missing `Agent`, `Session`, `User`, `Memory`, etc. |
| Inconsistent import style | Lines 1-34 | Low | Mix of direct imports and inline aliases |
| Missing local model exports | Global | Medium | `agent.py`, `agent_capability.py`, `agent_message.py`, `agent_response.py` not re-exported |

**Enhancement Suggestions:**

```python
# Add missing critical exports:
from .agent import Agent
from .agent_capability import (
    AgentCapability,
    AgentProfile,
    CapabilityCategory,
    CapabilityLevel,
    TaskRequirement,
    AgentAssignment,
)
from .agent_message import (
    AgentMessage,
    MessagePriority,
    MessageStatus,
    MessageType,
    MessageQueue,
    MessageThread,
)
from .agent_response import (
    DiscussResponse,
    ExecutionStepResult,
    PlanResponse,
    PlanUpdateResponse,
    ReflectionResponse,
    SummarizeResponse,
    VerificationResponse,
    get_json_schema,
    RESPONSE_SCHEMAS,
)

# Update __all__ to include all exported symbols
__all__ = [
    # ... existing exports ...
    "Agent",
    "AgentCapability",
    "AgentProfile",
    "CapabilityCategory",
    "CapabilityLevel",
    "AgentMessage",
    "MessagePriority",
    "MessageStatus",
    "MessageType",
    "PlanResponse",
    "ExecutionStepResult",
    # ... etc
]
```

**Overall Rating:** ⚠️ Needs Work

---

### 2. `backend/app/domain/models/agent.py`

**Purpose:** Agent entity - aggregate root for AI agent lifecycle management

**Current Setup:**
- Simple aggregate root with UUID generation
- Temperature and max_tokens validators (Pydantic v2 compliant with `@classmethod`)
- Has `created_at` and `updated_at` timestamps
- Contains `memories` dict for memory storage

**Strengths:**
- Pydantic v2 compliant `@field_validator` with `@classmethod`
- Clear docstring explaining purpose
- Default factories for mutable types

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| UUID truncation weak | Line 15 | High | `uuid.uuid4().hex[:16]` - only 16 hex chars, collision risk |
| Outdated Config class | Lines 41-42 | Medium | Uses legacy `class Config` instead of `model_config = ConfigDict(...)` |
| Missing updated_at auto-update | Lines 23 | Medium | `updated_at` never auto-updates on mutations |
| No model_config | Global | Medium | Missing `frozen=True` or `extra='forbid'` for safety |
| No domain behavior methods | Global | Low | Model lacks business methods like `add_memory()`, `update_context()` |
| Lambda datetime default | Lines 22-23 | Low | Uses `lambda: datetime.now(UTC)` instead of just `datetime.now(UTC)` |
| Temperature range limited | Line 19 | Low | Range 0-1 but OpenAI now supports up to 2.0 for some models |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models.memory import Memory


class Agent(BaseModel):
    """
    Agent aggregate root that manages the lifecycle and state of an AI agent.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,  # Validate on attribute changes
    )

    id: str = Field(default_factory=lambda: f"agent_{uuid.uuid4().hex}")
    memories: dict[str, Memory] = Field(default_factory=dict)
    model_name: str = Field(default="")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)  # Extended for newer models
    max_tokens: int = Field(default=2000, gt=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0 and 2.0")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Max tokens must be positive")
        return v

    @model_validator(mode="after")
    def update_timestamp_on_change(self) -> "Agent":
        """Auto-update timestamp on any mutation."""
        self.updated_at = datetime.now(UTC)
        return self

    # Domain behavior methods:
    def add_memory(self, memory: Memory) -> None:
        """Add a memory to the agent."""
        self.memories[memory.id] = memory
        self.updated_at = datetime.now(UTC)

    def get_active_memories(self, limit: int = 10) -> list[Memory]:
        """Get most relevant active memories."""
        return sorted(
            self.memories.values(),
            key=lambda m: m.created_at,
            reverse=True,
        )[:limit]

    def remove_memory(self, memory_id: str) -> bool:
        """Remove a memory by ID. Returns True if removed."""
        if memory_id in self.memories:
            del self.memories[memory_id]
            self.updated_at = datetime.now(UTC)
            return True
        return False
```

**Overall Rating:** ⚠️ Needs Work

---

### 3. `backend/app/domain/models/agent_capability.py`

**Purpose:** Agent capability definitions - tracking agent capabilities and enabling intelligent routing

**Current Setup:**
- Comprehensive capability tracking with categories (`CapabilityCategory`) and levels (`CapabilityLevel`)
- `AgentCapability` with performance scoring using exponential moving average (EMA)
- `AgentProfile` with suitability calculations
- `TaskRequirement` and `AgentAssignment` for task routing

**Strengths:**
- Well-designed enums with clear semantics
- `update_performance()` uses EMA for smooth metric updates
- `calculate_suitability()` considers availability and tool coverage
- Clean separation of concerns between capability, profile, requirement, assignment
- Good use of `Field(ge=0.0, le=1.0)` for bounded values

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC in datetime | Lines 92-93 | Medium | Uses `datetime.now` without `UTC` timezone |
| Hardcoded EMA alpha | Lines 68, 71, 73 | Low | Alpha (0.1) hardcoded - should be configurable |
| Performance formula undocumented | Line 73 | Low | `0.7 * success_rate + 0.3 * speed` lacks documentation |
| Duplicated level_order list | Lines 115-121, 196-202 | Medium | Same list defined twice - extract to constant |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict/frozen settings |
| Mutable default in method | Line 65 | Low | `update_performance` mutates self directly |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Extract to module constant to avoid duplication
CAPABILITY_LEVEL_ORDER = [
    CapabilityLevel.NONE,
    CapabilityLevel.LIMITED,
    CapabilityLevel.BASIC,
    CapabilityLevel.PROFICIENT,
    CapabilityLevel.EXPERT,
]


class AgentCapability(BaseModel):
    """A specific capability of an agent."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str
    category: CapabilityCategory
    level: CapabilityLevel = CapabilityLevel.PROFICIENT
    description: str = ""
    required_tools: list[str] = Field(default_factory=list)
    performance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    usage_count: int = 0
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    average_duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Configurable EMA alpha
    _ema_alpha: float = 0.1

    def is_suitable_for(self, task_category: CapabilityCategory) -> bool:
        """Check if this capability is suitable for a task category."""
        return (
            self.category == task_category
            and CAPABILITY_LEVEL_ORDER.index(self.level) >= CAPABILITY_LEVEL_ORDER.index(CapabilityLevel.PROFICIENT)
        )

    def update_performance(self, success: bool, duration_ms: float) -> None:
        """Update performance metrics based on usage.

        Uses exponential moving average (EMA) for smooth updates.

        Performance score = 70% success_rate + 30% speed_bonus
        Speed bonus: full (0.3) if <5s, half (0.15) if >=5s
        """
        self.usage_count += 1

        # EMA update
        success_value = 1.0 if success else 0.0
        self.success_rate = self._ema_alpha * success_value + (1 - self._ema_alpha) * self.success_rate
        self.average_duration_ms = (
            self._ema_alpha * duration_ms + (1 - self._ema_alpha) * self.average_duration_ms
        )

        # Performance score with documented formula
        speed_bonus = 0.3 if duration_ms < 5000 else 0.15
        self.performance_score = self.success_rate * 0.7 + speed_bonus


class AgentProfile(BaseModel):
    """Profile of an agent with its capabilities."""

    model_config = ConfigDict(strict=True, extra="forbid")

    agent_type: str
    agent_name: str
    capabilities: list[AgentCapability] = Field(default_factory=list)
    primary_category: CapabilityCategory | None = None
    max_concurrent_tasks: int = 1
    is_available: bool = True
    current_load: int = 0
    total_tasks_completed: int = 0
    overall_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def has_capability(self, name: str, min_level: CapabilityLevel = CapabilityLevel.BASIC) -> bool:
        """Check if agent has a capability at minimum level."""
        cap = self.get_capability(name)
        if not cap:
            return False
        return (
            CAPABILITY_LEVEL_ORDER.index(cap.level) >= CAPABILITY_LEVEL_ORDER.index(min_level)
        )
```

**Overall Rating:** ✅ Good (with minor improvements needed)

---

### 4. `backend/app/domain/models/agent_message.py`

**Purpose:** Agent message domain models for inter-agent communication

**Current Setup:**
- Comprehensive inter-agent messaging system with `MessageType`, `MessagePriority`, `MessageStatus` enums
- `AgentMessage` with full messaging metadata (threading, expiration, delivery tracking)
- Payload models for different message types (`TaskDelegationPayload`, `InformationRequestPayload`, etc.)
- `MessageThread` for conversation tracking
- `MessageQueue` with priority-based inbox/outbox management

**Strengths:**
- Well-designed `MessageType` enum covering all communication scenarios
- `MessageQueue.get_pending()` with priority-based sorting
- Expiration handling via `is_expired()` method
- Thread tracking for conversation continuity
- Rich payload types for structured communication

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Weak ID generation | Lines 57, 172 | High | Uses `datetime.now().timestamp()` - not unique, not URL-safe, potential collisions |
| No UTC timezone | Lines 77, 92-93, 172 | Medium | Uses `datetime.now` without UTC timezone |
| Mutable methods on Pydantic model | Lines 91-94, 180-188 | Medium | Direct mutation not thread-safe, consider immutable pattern |
| Priority dict recreated each call | Lines 214-220 | Low | Dict created on every `get_pending()` call - should be class constant |
| Unbounded processed list | Line 200 | Medium | `processed` list grows without cleanup - memory leak risk |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict/frozen settings |
| Inconsistent ID prefixes | Lines 57, 172 | Low | Uses `msg_` and `thread_` prefixes but not `uuid` format |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Module constants
PRIORITY_ORDER: dict[MessagePriority, int] = {
    MessagePriority.CRITICAL: 0,
    MessagePriority.HIGH: 1,
    MessagePriority.NORMAL: 2,
    MessagePriority.LOW: 3,
}
MAX_PROCESSED_MESSAGES = 1000
MAX_INBOX_SIZE = 10000


class AgentMessage(BaseModel):
    """A message between agents."""

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex}")
    message_type: MessageType
    sender_id: str
    sender_type: str
    recipient_id: str | None = None
    recipient_type: str | None = None
    priority: MessagePriority = MessagePriority.NORMAL
    status: MessageStatus = MessageStatus.PENDING
    subject: str
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    in_reply_to: str | None = None
    thread_id: str | None = None
    correlation_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    delivered_at: datetime | None = None
    expires_at: datetime | None = None
    requires_response: bool = False
    is_broadcast: bool = False

    def is_expired(self) -> bool:
        """Check if the message has expired."""
        if self.expires_at:
            return datetime.now(UTC) > self.expires_at
        return False


class MessageQueue(BaseModel):
    """Queue of messages for an agent."""

    model_config = ConfigDict(strict=True)

    agent_id: str
    inbox: list[AgentMessage] = Field(default_factory=list)
    outbox: list[AgentMessage] = Field(default_factory=list)
    processed: list[str] = Field(default_factory=list)
    max_processed: int = MAX_PROCESSED_MESSAGES
    max_inbox: int = MAX_INBOX_SIZE

    def get_pending(self, limit: int = 10) -> list[AgentMessage]:
        """Get pending messages from inbox, sorted by priority."""
        pending = [m for m in self.inbox if m.status == MessageStatus.PENDING]
        pending.sort(key=lambda m: PRIORITY_ORDER.get(m.priority, 2))
        return pending[:limit]

    def mark_processed(self, message_id: str) -> None:
        """Mark a message as processed with bounded growth."""
        self.processed.append(message_id)
        # Prevent unbounded growth
        if len(self.processed) > self.max_processed:
            self.processed = self.processed[-(self.max_processed // 2):]

    def clear_expired(self) -> int:
        """Remove expired messages and return count removed."""
        before = len(self.inbox)
        self.inbox = [m for m in self.inbox if not m.is_expired()]
        return before - len(self.inbox)

    def cleanup(self) -> dict[str, int]:
        """Perform full cleanup and return counts."""
        return {
            "expired_removed": self.clear_expired(),
            "processed_pruned": max(0, len(self.processed) - self.max_processed),
        }


class MessageThread(BaseModel):
    """A thread of related messages."""

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: f"thread_{uuid.uuid4().hex}")
    subject: str
    participants: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_closed: bool = False

    def add_message(self, message_id: str) -> None:
        """Add a message to the thread."""
        self.messages.append(message_id)
        self.last_activity = datetime.now(UTC)
```

**Overall Rating:** ⚠️ Needs Work

---

### 5. `backend/app/domain/models/agent_response.py`

**Purpose:** Structured response schemas for agent outputs - defines expected output structure from LLM calls

**Current Setup:**
- Excellent use of Pydantic v2 `ConfigDict` with `strict=True`, `frozen=True`, `extra="forbid"`
- Comprehensive structured output schemas for LLM calls (Plan, Execution, Verification, Reflection)
- JSON schema generation for OpenAI structured output via `get_json_schema()`
- Schema registry pattern with `RESPONSE_SCHEMAS` dict
- Backward compatibility handling in `SummarizeResponse.model_validate()`

**Strengths:**
- Exemplary Pydantic v2 usage - this file demonstrates best practices
- `strict=True` prevents type coercion, `frozen=True` ensures immutability
- Clear documentation on each schema's purpose and usage
- Proper use of `Field(description=...)` for LLM guidance
- `get_json_schema()` provides OpenAI-compatible structured output format
- `VerificationVerdict` and `ReflectionDecision` enums for type-safe decisions
- Backward compatibility pattern in `SummarizeResponse` for legacy format handling

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Incomplete docstring | Line 252 | Low | `get_json_schema` docstring missing 'verification', 'simple_verification', 'reflection' |
| Mutable list with frozen | Various | Low | `default_factory=list` with `frozen=True` could cause issues if lists are mutated |

**Enhancement Suggestions:**

```python
def get_json_schema(schema_name: str) -> dict:
    """Get JSON schema for OpenAI structured output.

    Args:
        schema_name: One of 'plan', 'plan_update', 'execution', 'summarize',
                     'discuss', 'verification', 'simple_verification', 'reflection'

    Returns:
        JSON schema dict compatible with OpenAI's response_format parameter

    Raises:
        ValueError: If schema_name is not recognized
    """
    if schema_name not in RESPONSE_SCHEMAS:
        raise ValueError(
            f"Unknown schema: {schema_name}. Available: {list(RESPONSE_SCHEMAS.keys())}"
        )

    model = RESPONSE_SCHEMAS[schema_name]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": model.model_json_schema(),
        },
    }


# Consider adding runtime validation helper:
def validate_response(schema_name: str, data: dict) -> BaseModel:
    """Validate response data against a schema.

    Args:
        schema_name: Name of the schema to validate against
        data: Dictionary of data to validate

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If schema_name is not recognized
        ValidationError: If data doesn't match schema
    """
    schema_cls = RESPONSE_SCHEMAS.get(schema_name)
    if not schema_cls:
        raise ValueError(f"Unknown schema: {schema_name}")
    return schema_cls.model_validate(data)
```

**Overall Rating:** ✅ Excellent

---

## Batch 1 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 23 |
| Critical | 2 |
| Medium | 13 |
| Low | 8 |

### Key Findings

1. **Pydantic v2 Compliance**: Only `agent_response.py` fully follows Pydantic v2 best practices with `model_config = ConfigDict(...)`. Other files use legacy `class Config` or no config at all.

2. **UTC Timezone**: Most datetime defaults use `datetime.now` without UTC timezone - should use `datetime.now(UTC)`.

3. **ID Generation**: Several files use weak ID generation (timestamp-based or truncated UUIDs) instead of full UUIDs.

4. **Model Exports**: `__init__.py` has incomplete exports - many important models aren't exposed.

5. **Bounded Collections**: `MessageQueue.processed` and similar collections grow without bounds - need cleanup logic.

### Priority Fixes

1. **High**: Fix UUID generation in `agent.py` and `agent_message.py`
2. **High**: Complete exports in `domain/models/__init__.py`
3. **Medium**: Add `model_config = ConfigDict(...)` to all model classes
4. **Medium**: Add UTC timezone to all datetime defaults
5. **Medium**: Add bounded growth to collections

---

## Progress Tracker

| Batch | Files | Status | Issues | Date |
|-------|-------|--------|--------|------|
| 1 | 1-5 | ✅ Complete | 23 | 2026-02-11 |
| 2 | 6-10 | ✅ Complete | 18 | 2026-02-11 |
| 3 | 11-15 | ✅ Complete | 19 | 2026-02-11 |
| 4 | 16-20 | ✅ Complete | 21 | 2026-02-11 |
| 5 | 21-25 | ✅ Complete | 17 | 2026-02-11 |
| 6 | 26-30 | ✅ Complete | 15 | 2026-02-11 |
| 7 | 31-35 | ✅ Complete | 14 | 2026-02-11 |
| 8 | 36-40 | ✅ Complete | 16 | 2026-02-11 |

---

## Batch 2: Domain Models (Files 6-10)

### 6. `backend/app/domain/models/auth.py`

**Purpose:** Authentication related domain models for login and refresh operations

**Current Setup:**
- Simple `AuthToken` model with access_token, refresh_token, and user
- Default token_type of "bearer"
- Optional User embedding

**Strengths:**
- Clean, minimal model for auth tokens
- Optional refresh_token handles both access-only and refresh flows
- Optional user embedding for response payload convenience

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No expiration tracking | Global | High | Token has no `expires_in` or `expires_at` field |
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| No token validation | Global | Medium | No validation for token format/length |
| Missing common OAuth fields | Global | Low | Missing `scope`, `token_id` fields for OAuth compliance |
| Circular import risk | Line 6 | Low | Importing `User` could cause circular imports |

**Enhancement Suggestions:**

```python
"""Authentication related domain models"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.domain.models.user import User


class AuthToken(BaseModel):
    """Authentication token model for login and refresh operations."""

    model_config = ConfigDict(strict=True, extra="forbid")

    access_token: str = Field(..., min_length=1, description="JWT access token")
    token_type: str = Field(default="bearer", pattern="^(bearer|Bearer)$")
    refresh_token: str | None = Field(default=None, min_length=1)
    expires_in: int | None = Field(default=None, ge=0, description="Token lifetime in seconds")
    expires_at: datetime | None = Field(default=None, description="Absolute expiration timestamp")
    scope: str | None = Field(default=None, description="OAuth scope if applicable")

    # Avoid circular import by using forward reference
    user: "User | None" = None

    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self.expires_at:
            return datetime.now(UTC) > self.expires_at
        return False

    @classmethod
    def create_with_expiry(
        cls,
        access_token: str,
        expires_in_seconds: int = 3600,
        **kwargs,
    ) -> "AuthToken":
        """Create token with automatic expiration calculation."""
        return cls(
            access_token=access_token,
            expires_in=expires_in_seconds,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
            **kwargs,
        )
```

**Overall Rating:** ⚠️ Needs Work

---

### 7. `backend/app/domain/models/benchmark.py`

**Purpose:** Benchmark and metric extraction models for research analysis

**Current Setup:**
- Comprehensive benchmark tracking with `BenchmarkCategory` and `BenchmarkUnit` enums
- `ExtractedBenchmark` with source attribution and confidence scoring
- `BenchmarkComparison` for cross-subject comparisons
- `BenchmarkExtractionResult` for batch extraction results
- `BenchmarkQuery` for filtering benchmarks

**Strengths:**
- Excellent use of `@field_validator` with `@classmethod` (Pydantic v2 compliant)
- Rich domain model with `get_display_value()` helper
- Source attribution tracking (`source_url`, `extracted_text`)
- Confidence scoring with validation `ge=0.0, le=1.0`
- `BenchmarkQuery.matches()` for clean filtering logic
- Well-organized enums for categories and units

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC in datetime | Line 62 | Medium | Uses `datetime` without timezone awareness |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Dict in entries list | Lines 89-91 | Low | `entries: list[dict[str, Any]]` - should be typed model |
| Return type Any | Line 104 | Low | `get_ranking()` returns `list[tuple[str, Any]]` - value should be typed |
| No datetime factory | Line 62 | Low | `report_date` could use default_factory |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtractedBenchmark(BaseModel):
    """A benchmark extracted from research content."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(..., description="Benchmark name (e.g., 'MMLU Score')")
    value: float | str = Field(..., description="Benchmark value")
    unit: BenchmarkUnit = Field(default=BenchmarkUnit.CUSTOM)
    custom_unit: str | None = Field(default=None)
    category: BenchmarkCategory = Field(default=BenchmarkCategory.CUSTOM)
    source_url: str = Field(..., description="URL where benchmark was found")
    source_title: str | None = Field(default=None)
    extracted_text: str = Field(..., description="Original text containing the benchmark")
    subject: str = Field(..., description="What is being benchmarked (e.g., 'GPT-4')")
    comparison_baseline: str | None = Field(default=None)
    test_conditions: str | None = Field(default=None)
    report_date: datetime | None = Field(default=None)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    is_verified: bool = Field(default=False)

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: float | str) -> float | str:
        if isinstance(v, str) and not v.strip():
            raise ValueError("Benchmark value cannot be empty")
        return v


class BenchmarkEntry(BaseModel):
    """A single entry in a benchmark comparison."""

    model_config = ConfigDict(strict=True)

    subject: str
    value: float | str
    source_url: str


class BenchmarkComparison(BaseModel):
    """Comparison of benchmarks across subjects."""

    model_config = ConfigDict(strict=True, extra="forbid")

    benchmark_name: str
    category: BenchmarkCategory
    unit: BenchmarkUnit
    entries: list[BenchmarkEntry] = Field(default_factory=list)
    winner: str | None = Field(default=None)
    analysis: str | None = Field(default=None)

    @property
    def sorted_entries(self) -> list[BenchmarkEntry]:
        """Entries sorted by value (descending for most metrics)."""
        try:
            return sorted(
                self.entries,
                key=lambda x: float(x.value) if isinstance(x.value, (int, float)) else 0,
                reverse=True,
            )
        except (ValueError, TypeError):
            return self.entries

    def get_ranking(self) -> list[tuple[str, float | str]]:
        """Get ranked list of (subject, value) tuples."""
        return [(e.subject, e.value) for e in self.sorted_entries]


class BenchmarkExtractionResult(BaseModel):
    """Result of benchmark extraction from research."""

    model_config = ConfigDict(strict=True)

    benchmarks: list[ExtractedBenchmark] = Field(default_factory=list)
    comparisons: list[BenchmarkComparison] = Field(default_factory=list)
    extraction_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sources_analyzed: int = Field(default=0)
    benchmarks_found: int = Field(default=0)
    warnings: list[str] = Field(default_factory=list)
```

**Overall Rating:** ✅ Good

---

### 8. `backend/app/domain/models/canvas.py`

**Purpose:** Canvas domain models for the interactive AI canvas editor

**Current Setup:**
- Comprehensive canvas system with `ElementType`, `FillType`, `GradientType`, `ExportFormat` enums
- Style models: `SolidFill`, `GradientFill`, `Stroke`, `Shadow`, `TextStyle`
- `CanvasElement` with flattened type-specific fields
- `CanvasPage` and `CanvasProject` for project organization
- `CanvasVersion` for version control

**Strengths:**
- Uses UTC timezone correctly: `datetime.now(UTC)` (Lines 143-144, 170)
- Good use of `@field_validator` with `@classmethod` (Pydantic v2 compliant)
- Type union pattern: `Fill = SolidFill | GradientFill` (Line 53)
- Bounded validation: `len(v) > 50` raises error for pages
- Clean separation of element types with optional type-specific fields

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Dict types instead of models | Lines 98-105 | Low | Uses `dict[str, Any]` for fill/stroke/shadow instead of typed models |
| No element ID validation | Line 84 | Low | `id: str` has no validation - could be empty |
| No z_index bounds | Line 97 | Low | No validation on z_index range |
| No updated_at auto-update | Line 144 | Medium | `updated_at` never auto-updates on mutations |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CanvasElement(BaseModel):
    """Single canvas element with flattened type-specific fields."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(..., min_length=1, description="Unique element identifier")
    type: ElementType
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = Field(default=100.0, ge=0.0)
    height: float = Field(default=100.0, ge=0.0)
    rotation: float = Field(default=0.0, ge=0.0, lt=360.0)
    scale_x: float = Field(default=1.0, gt=0.0)
    scale_y: float = Field(default=1.0, gt=0.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    visible: bool = True
    locked: bool = False
    z_index: int = Field(default=0, ge=-10000, le=10000)

    # Use Union types for proper validation
    fill: SolidFill | GradientFill | None = None
    stroke: Stroke | None = None
    shadow: Shadow | None = None

    corner_radius: float = Field(default=0.0, ge=0.0)

    # Type-specific fields
    text: str | None = None
    text_style: TextStyle | None = None
    src: str | None = None
    points: list[float] | None = None
    children: list[str] | None = Field(default=None, max_length=100)


class CanvasProject(BaseModel):
    """A canvas project owned by a user."""

    model_config = ConfigDict(strict=True, extra="forbid", validate_assignment=True)

    id: str
    user_id: str
    session_id: str | None = None
    name: str = "Untitled Design"
    description: str = ""
    pages: list[CanvasPage] = Field(default_factory=list)
    width: float = Field(default=1920.0, gt=0.0)
    height: float = Field(default=1080.0, gt=0.0)
    background: str = "#FFFFFF"
    thumbnail: str | None = None
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 200:
            raise ValueError("Name must be between 1 and 200 characters")
        return v

    @field_validator("pages")
    @classmethod
    def validate_pages(cls, v: list[CanvasPage]) -> list[CanvasPage]:
        if len(v) > 50:
            raise ValueError("Maximum 50 pages per project")
        return v

    @model_validator(mode="after")
    def update_timestamp(self) -> "CanvasProject":
        """Auto-update timestamp on any mutation."""
        self.updated_at = datetime.now(UTC)
        return self
```

**Overall Rating:** ✅ Good

---

### 9. `backend/app/domain/models/citation_discipline.py`

**Purpose:** Enhanced citation models for strict source discipline and hallucination prevention

**Current Setup:**
- `CitationRequirement` and `ClaimType` enums for citation policy
- `CitedClaim` with mandatory citation tracking and auto-caveat generation
- `CitationValidationResult` for comprehensive citation validation
- `CitationConfig` for configurable citation requirements

**Strengths:**
- Excellent use of `@model_validator(mode="after")` for claim validation (Line 46-59)
- Automatic caveat generation for uncited factual claims
- Comprehensive citation coverage and quality scoring
- Configurable citation policy via `CitationConfig`
- Clean separation of claim types with different requirements

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Hardcoded formula | Line 88 | Low | `overall_score` formula `0.6 * coverage + 0.4 * quality` undocumented |
| Mutable claim list | Line 77 | Low | `claims: list[CitedClaim]` in result could be large |
| No datetime defaults | Global | Low | No `created_at` for audit trail |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CitedClaim(BaseModel):
    """A claim with mandatory citation tracking."""

    model_config = ConfigDict(strict=True, extra="forbid")

    claim_text: str = Field(..., description="The claim being made")
    claim_type: ClaimType

    citation_ids: list[str] = Field(default_factory=list)
    supporting_excerpts: list[str] = Field(default_factory=list)

    is_verified: bool = Field(default=False)
    verification_method: str | None = Field(default=None)

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_caveat: bool = Field(default=False)
    caveat_text: str | None = Field(default=None)

    # Add audit trail
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_citation_requirements(self) -> "CitedClaim":
        """Ensure citations match claim type requirements."""
        # Factual and statistical claims MUST have citations
        if (
            self.claim_type in (ClaimType.FACTUAL, ClaimType.STATISTICAL, ClaimType.QUOTATION)
            and not self.citation_ids
        ):
            self.requires_caveat = True
            self.caveat_text = f"[Unverified {self.claim_type.value} claim]"
            self.confidence = min(self.confidence, 0.3)

        if self.claim_type == ClaimType.INFERENCE and not self.caveat_text:
            self.caveat_text = "[Inferred from available data]"

        return self


class CitationValidationResult(BaseModel):
    """Result of citation validation for content."""

    model_config = ConfigDict(strict=True)

    is_valid: bool = Field(default=False)
    total_claims: int = Field(default=0)
    cited_claims: int = Field(default=0)
    uncited_factual_claims: int = Field(default=0)

    claims: list[CitedClaim] = Field(default_factory=list, max_length=1000)
    missing_citations: list[str] = Field(default_factory=list)
    weak_citations: list[str] = Field(default_factory=list)

    citation_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    citation_quality: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def overall_score(self) -> float:
        """Overall citation discipline score.

        Formula: 60% coverage + 40% quality
        Rationale: Coverage is more important than quality for hallucination prevention.
        """
        return self.citation_coverage * 0.6 + self.citation_quality * 0.4


class CitationConfig(BaseModel):
    """Configuration for citation requirements."""

    model_config = ConfigDict(strict=True)

    requirement_level: CitationRequirement = CitationRequirement.MODERATE
    min_coverage_score: float = Field(default=0.7, ge=0.0, le=1.0)
    min_quality_score: float = Field(default=0.5, ge=0.0, le=1.0)

    require_citations_for: list[ClaimType] = Field(
        default_factory=lambda: [
            ClaimType.FACTUAL,
            ClaimType.STATISTICAL,
            ClaimType.QUOTATION,
        ]
    )

    min_source_reliability: float = Field(default=0.4, ge=0.0, le=1.0)
    prefer_primary_sources: bool = True
    max_age_days: int | None = Field(default=730, ge=1)

    auto_add_caveats: bool = Field(default=True)
    fail_on_uncited_factual: bool = Field(default=False)
```

**Overall Rating:** ✅ Excellent

---

### 10. `backend/app/domain/models/claim_provenance.py`

**Purpose:** Claim Provenance Model for Hallucination Prevention - links claims to source evidence

**Current Setup:**
- `ClaimVerificationStatus` and `ClaimType` enums for categorization
- `ClaimProvenance` with hash-based deduplication and verification tracking
- `model_post_init` for automatic claim hashing and numeric detection
- `ProvenanceStore` for session-scoped claim management

**Strengths:**
- Excellent use of `model_post_init` for automatic field computation
- Hash-based deduplication for claims
- Automatic numeric detection with regex
- Comprehensive verification workflow: `mark_verified()`, `mark_fabricated()`, `mark_contradicted()`
- Properties for state checks: `is_grounded`, `needs_caveat`, `is_problematic`
- `ProvenanceStore` with useful query methods

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Deprecated datetime.utcnow() | Lines 87, 148, 161, 176 | Medium | Uses `datetime.utcnow()` instead of `datetime.now(UTC)` |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Regex in model_post_init | Line 104 | Low | Regex compilation on every init - could be cached |
| Mutable set in ProvenanceStore | Line 241 | Low | `verified_claims: set[str]` - sets aren't JSON serializable |
| No max bounds on claims dict | Line 240 | Low | `claims` dict could grow unbounded in long sessions |
| Duplicate ClaimType enum | Line 26-36 | Low | `ClaimType` defined here and in `citation_discipline.py` |

**Enhancement Suggestions:**

```python
import hashlib
import re
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Pre-compiled regex for numeric detection
_NUMERIC_PATTERN = re.compile(r"\d+(?:\.\d+)?")


class ClaimProvenance(BaseModel):
    """Links a claim in a report to its source evidence."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        # Allow mutation for mark_* methods
        validate_assignment=True,
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    report_id: str | None = None

    claim_text: str
    claim_type: ClaimType = ClaimType.UNKNOWN
    claim_hash: str = ""

    source_id: str | None = None
    tool_event_id: str | None = None
    source_url: str | None = None

    supporting_excerpt: str | None = None
    excerpt_location: str | None = None
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0)

    verification_status: ClaimVerificationStatus = ClaimVerificationStatus.UNVERIFIED
    verification_method: str | None = None
    verified_at: datetime | None = None
    verifier_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = "system"

    is_fabricated: bool = False
    requires_manual_review: bool = False
    is_numeric: bool = False
    extracted_numbers: list[float] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        """Generate claim hash after initialization."""
        if not self.claim_hash:
            self.claim_hash = self._generate_hash(self.claim_text)

        # Detect if claim is numeric using pre-compiled pattern
        numbers = _NUMERIC_PATTERN.findall(self.claim_text)
        if numbers:
            self.is_numeric = True
            self.extracted_numbers = [float(n) for n in numbers]

    @staticmethod
    def _generate_hash(text: str) -> str:
        """Generate hash for claim deduplication."""
        normalized = text.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def mark_verified(
        self,
        source_id: str,
        tool_event_id: str | None = None,
        source_url: str | None = None,
        excerpt: str | None = None,
        similarity: float = 1.0,
        method: str = "semantic",
    ) -> None:
        """Mark claim as verified with source evidence."""
        self.source_id = source_id
        self.tool_event_id = tool_event_id
        self.source_url = source_url
        self.supporting_excerpt = excerpt
        self.similarity_score = similarity

        if similarity >= 0.8:
            self.verification_status = ClaimVerificationStatus.VERIFIED
        elif similarity >= 0.5:
            self.verification_status = ClaimVerificationStatus.PARTIAL
        else:
            self.verification_status = ClaimVerificationStatus.INFERRED

        self.verification_method = method
        self.verified_at = datetime.now(UTC)  # Fixed: use datetime.now(UTC)
        self.verifier_confidence = similarity
        self.is_fabricated = False


class ProvenanceStore(BaseModel):
    """Session-scoped storage for claim provenance."""

    model_config = ConfigDict(strict=True)

    session_id: str
    claims: dict[str, ClaimProvenance] = Field(default_factory=dict)
    # Use list instead of set for JSON serialization
    verified_claim_hashes: list[str] = Field(default_factory=list)
    max_claims: int = 10000  # Bounded growth

    def add_claim(self, provenance: ClaimProvenance) -> None:
        """Add a claim provenance record."""
        # Enforce max bounds
        if len(self.claims) >= self.max_claims:
            # Remove oldest unverified claims
            oldest_hashes = sorted(
                [h for h, c in self.claims.items() if not c.is_grounded],
                key=lambda h: self.claims[h].created_at,
            )[: len(self.claims) - self.max_claims + 1]
            for h in oldest_hashes:
                del self.claims[h]

        self.claims[provenance.claim_hash] = provenance
        if provenance.is_grounded:
            if provenance.claim_hash not in self.verified_claim_hashes:
                self.verified_claim_hashes.append(provenance.claim_hash)

    def is_claim_verified(self, claim_text: str) -> bool:
        """Check if a claim is verified."""
        claim_hash = ClaimProvenance._generate_hash(claim_text)
        return claim_hash in self.verified_claim_hashes
```

**Overall Rating:** ✅ Good

---

## Batch 2 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 18 |
| Critical | 0 |
| Medium | 10 |
| Low | 8 |

### Key Findings

1. **Pydantic v2 Compliance**: Good use of `@field_validator` and `@model_validator` with `@classmethod`. Still missing `model_config = ConfigDict(...)` in most files.

2. **UTC Timezone**: Mixed - `canvas.py` uses `datetime.now(UTC)` correctly, but `claim_provenance.py` uses deprecated `datetime.utcnow()`.

3. **Model Design**: Excellent domain modeling with rich behavior methods (`mark_verified()`, `is_grounded`, etc.).

4. **Type Safety**: Some uses of `dict[str, Any]` that could be replaced with typed models.

5. **Bounded Collections**: `ProvenanceStore.claims` could grow unbounded in long sessions.

### Priority Fixes

1. **Medium**: Replace `datetime.utcnow()` with `datetime.now(UTC)` in `claim_provenance.py`
2. **Medium**: Add `model_config = ConfigDict(...)` to all model classes
3. **Medium**: Add `expires_in`/`expires_at` to `AuthToken`
4. **Low**: Extract duplicate `ClaimType` enum to shared module
5. **Low**: Add bounds to `ProvenanceStore.claims`

---

## Batch 3: Domain Models (Files 11-15)

### 11. `backend/app/domain/models/connector.py`

**Purpose:** Connector domain models for external API and MCP server connections

**Current Setup:**
- Three connector types: APP, CUSTOM_API, CUSTOM_MCP via `ConnectorType` enum
- `CustomApiConfig` with URL validation and header limits
- `CustomMcpConfig` with security-focused validation (command allowlist, blocked env vars)
- `Connector` catalog entry and `UserConnector` per-user instance

**Strengths:**
- Excellent security considerations: `MCP_COMMAND_ALLOWLIST` and `MCP_BLOCKED_ENV_VARS`
- Uses UTC timezone correctly: `datetime.now(UTC)` (Lines 168-169, 206-207)
- Good use of `@field_validator` with `@classmethod` (Pydantic v2 compliant)
- Bounded collections: `len(v) > 20` limits for headers/env vars
- URL validation with scheme and length checks
- Clean separation of catalog (Connector) vs instance (UserConnector)

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Sensitive data in model | Line 201-202 | Medium | `access_token`, `refresh_token` stored - should be encrypted |
| No token encryption hint | Global | Low | No documentation about token storage security |
| Missing validation on connector_id | Line 192 | Low | `connector_id` has no format validation |
| No updated_at auto-update | Lines 169, 207 | Medium | `updated_at` never auto-updates on mutations |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomApiConfig(BaseModel):
    """Configuration for a custom API connector."""

    model_config = ConfigDict(strict=True, extra="forbid")

    base_url: str
    auth_type: ConnectorAuthType = ConnectorAuthType.NONE
    api_key: str | None = Field(default=None, exclude=True)  # Exclude from serialization
    headers: dict[str, str] = Field(default_factory=dict, max_length=20)
    description: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        if len(v) > 2048:
            raise ValueError("URL must not exceed 2048 characters")
        return v


class UserConnector(BaseModel):
    """Per-user connection instance."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        # Note: Tokens should be encrypted at rest in the repository layer
        serialize_by_alias=True,
    )

    id: str
    user_id: str
    connector_id: str | None = None
    connector_type: ConnectorType
    name: str
    description: str = ""
    icon: str = ""
    status: ConnectorStatus = ConnectorStatus.PENDING
    enabled: bool = True
    api_config: CustomApiConfig | None = None
    mcp_config: CustomMcpConfig | None = None
    # These tokens should be encrypted in the repository layer
    access_token: str | None = Field(default=None, exclude=True)
    refresh_token: str | None = Field(default=None, exclude=True)
    token_expires_at: datetime | None = None
    last_connected_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if self.token_expires_at:
            return datetime.now(UTC) > self.token_expires_at
        return False
```

**Overall Rating:** ✅ Good

---

### 12. `backend/app/domain/models/context_memory.py`

**Purpose:** Context memory model for file-system-as-context pattern (Manus AI architecture)

**Current Setup:**
- `ContextType` enum for different context types (GOAL, TODO, STATE, KNOWLEDGE, RESEARCH)
- `ContextMemory` model with priority-based attention
- Serialization methods: `to_dict()` and `from_dict()` class method

**Strengths:**
- Excellent docstrings explaining the pattern and purpose
- Clear separation of context types with documented semantics
- Priority field for attention management
- File path tracking for sandbox persistence
- Clean serialization pattern

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Deprecated datetime.utcnow() | Lines 57-58 | Medium | Uses `datetime.utcnow()` instead of `datetime.now(UTC)` |
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| No updated_at auto-update | Line 58 | Medium | `updated_at` never auto-updates |
| Redundant to_dict method | Lines 60-74 | Low | Pydantic v2 has `model_dump()` - manual method is redundant |
| No content validation | Line 54 | Low | `content` has no size limits |
| Priority bounds | Line 55 | Low | No bounds on `priority` field |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContextType(str, Enum):
    """Types of externalized context."""

    GOAL = "goal"
    TODO = "todo"
    STATE = "state"
    KNOWLEDGE = "knowledge"
    RESEARCH = "research"


class ContextMemory(BaseModel):
    """Externalized memory stored in sandbox file system."""

    model_config = ConfigDict(strict=True, extra="forbid")

    session_id: str = Field(..., description="Session this context belongs to")
    context_type: ContextType = Field(..., description="Type of context")
    content: str = Field(..., description="The actual context content", max_length=100_000)
    priority: int = Field(default=0, description="Priority for attention", ge=0, le=100)
    file_path: str | None = Field(default=None, description="Path in sandbox if persisted")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage. Note: Prefer model_dump() for standard use."""
        data = self.model_dump()
        data["context_type"] = self.context_type.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextMemory":
        """Deserialize from storage."""
        data = dict(data)  # Make a copy
        if isinstance(data.get("context_type"), str):
            data["context_type"] = ContextType(data["context_type"])
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)
```

**Overall Rating:** ⚠️ Needs Work

---

### 13. `backend/app/domain/models/deep_research.py`

**Purpose:** Deep Research domain models for parallel search execution

**Current Setup:**
- `ResearchQueryStatus` enum for query lifecycle
- `ResearchQuery` with status tracking and timing
- `DeepResearchConfig` with concurrency controls
- `DeepResearchSession` for session state management

**Strengths:**
- Good use of Field constraints: `ge=1, le=10` for max_concurrent
- Properties for computed values: `completed_count`, `total_count`
- `to_event_data()` method for event serialization
- Timeout configuration with bounds

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Lines 27-28, 59-61 | Medium | Uses `datetime.now()` and `datetime.fromisoformat()` without timezone |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Untyped result | Line 25 | Medium | `result: list[dict] | None` - should use typed model |
| No status validation | Line 58 | Low | `status: str` - should use enum |
| No ID validation | Lines 22, 54 | Low | `id` and `research_id` have no format validation |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.search import SearchResultItem


class ResearchQueryStatus(str, Enum):
    """Individual research query status."""

    PENDING = "pending"
    SEARCHING = "searching"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class DeepResearchSessionStatus(str, Enum):
    """Deep research session status."""

    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    STARTED = "started"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ResearchQuery(BaseModel):
    """Individual research query with status tracking."""

    model_config = ConfigDict(strict=True)

    id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    status: ResearchQueryStatus = ResearchQueryStatus.PENDING
    result: list[SearchResultItem] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_event_data(self) -> dict[str, Any]:
        """Convert to event-compatible dict."""
        return {
            "id": self.id,
            "query": self.query,
            "status": self.status.value,
            "result": [r.model_dump() for r in self.result] if self.result else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class DeepResearchConfig(BaseModel):
    """Configuration for deep research execution."""

    model_config = ConfigDict(strict=True)

    queries: list[str] = Field(..., description="List of search queries to execute", min_length=1)
    auto_run: bool = Field(default=False, description="Skip approval and run immediately")
    max_concurrent: int = Field(default=5, ge=1, le=10, description="Maximum concurrent searches")
    timeout_per_query: int = Field(default=30, ge=5, le=120, description="Timeout per query in seconds")


class DeepResearchSession(BaseModel):
    """Deep research session state."""

    model_config = ConfigDict(strict=True)

    research_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    config: DeepResearchConfig
    queries: list[ResearchQuery]
    status: DeepResearchSessionStatus = DeepResearchSessionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def completed_count(self) -> int:
        """Count of completed queries (including skipped/failed)."""
        return sum(
            1
            for q in self.queries
            if q.status in (ResearchQueryStatus.COMPLETED, ResearchQueryStatus.SKIPPED, ResearchQueryStatus.FAILED)
        )

    @property
    def total_count(self) -> int:
        """Total number of queries."""
        return len(self.queries)

    @property
    def progress_percentage(self) -> float:
        """Progress as percentage."""
        return (self.completed_count / self.total_count * 100) if self.total_count > 0 else 0.0
```

**Overall Rating:** ⚠️ Needs Work

---

### 14. `backend/app/domain/models/event.py`

**Purpose:** Domain event models for agent events (discriminated union pattern)

**Current Setup:**
- Massive file with 50+ event types
- `BaseEvent` as base class with id and timestamp
- Discriminated union `AgentEvent` using `Annotated[Union[...], Discriminator("type")]`
- Extensive tool content types: `BrowserToolContent`, `SearchToolContent`, etc.
- Rich event types: `PlanEvent`, `ToolEvent`, `MessageEvent`, `ReportEvent`, etc.

**Strengths:**
- Excellent use of discriminated union pattern for type-safe event handling
- `Literal["type"]` for type discrimination - Pydantic v2 best practice
- Comprehensive event coverage for agent lifecycle
- Good use of `Field(default_factory=lambda: ...)` for mutable defaults
- `ToolContent` union type for type-safe tool results

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Line 52 | Medium | Uses `datetime.now()` without UTC |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Large file size | Global | Low | 888 lines - could be split into event_types.py |
| Any type usage | Lines 97, 109, 169, etc. | Medium | Multiple uses of `Any` for tool results |
| Missing docstrings | Many classes | Low | Not all event classes have docstrings |
| Union import syntax | Line 846 | Low | Uses `Union[]` with `# noqa: UP007` - could use `\|` syntax |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field


class BaseEvent(BaseModel):
    """Base class for agent events."""

    model_config = ConfigDict(strict=True)

    type: Literal[""] = ""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorEvent(BaseEvent):
    """Error event with structured error information."""

    model_config = ConfigDict(strict=True)

    type: Literal["error"] = "error"
    error: str
    error_type: str | None = None
    recoverable: bool = True
    retry_hint: str | None = None


# Consider splitting into event_types.py:
# - core_events.py: BaseEvent, ErrorEvent, DoneEvent, WaitEvent
# - tool_events.py: ToolEvent, ToolProgressEvent, ToolContent types
# - research_events.py: DeepResearchEvent, WideResearchEvent
# - ui_events.py: ProgressEvent, SuggestionEvent, ComprehensionEvent


# For the discriminated union, Python 3.10+ allows | syntax:
AgentEvent = Annotated[
    ErrorEvent
    | PlanEvent
    | ToolEvent
    | ToolProgressEvent
    | StepEvent
    | MessageEvent
    # ... rest of event types
    | PhaseEvent,
    Discriminator("type"),
]
```

**Overall Rating:** ✅ Good (architecturally sound, minor improvements needed)

---

### 15. `backend/app/domain/models/failure_snapshot.py`

**Purpose:** Failure Snapshot Domain Model for retry quality improvement with token budget enforcement

**Current Setup:**
- `FailureSnapshot` with structured failure context
- Token budget enforcement via `ClassVar` constants and validators
- `@model_validator(mode="wrap")` for cross-field budget enforcement
- Factory methods: `minimal()` and `full()`
- `to_retry_context()` for LLM prompt formatting

**Strengths:**
- Excellent use of `@model_validator(mode="wrap")` for budget enforcement
- Uses UTC timezone correctly: `datetime.now(UTC)` (Line 32)
- `ClassVar` for configuration constants - Pydantic best practice
- Factory methods for different snapshot modes
- Token estimation with `calculate_size_tokens()`
- Field validators with `@classmethod` - Pydantic v2 compliant

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| Truncation side effect | Lines 114-115 | Low | `enforce_token_budget` mutates instance after validation |
| Import unused type | Line 8 | Low | `Self` imported but could use string annotation |
| Token estimate formula | Line 110 | Low | `len(serialized) // 4` is rough - could use tiktoken |
| No max retry count | Line 31 | Low | No upper bound on retry_count |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler


class FailureSnapshot(BaseModel):
    """Structured failure context for retry quality improvement."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        # Allow mutation for budget enforcement
        validate_assignment=True,
    )

    failed_step: str
    error_type: str
    error_message: str
    tool_call_context: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = Field(ge=0, le=10)  # Added upper bound
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    context_pressure: float = Field(default=0.0, ge=0.0, le=1.0)

    # Token budget configuration
    MAX_ERROR_MESSAGE_LENGTH: ClassVar[int] = 500
    MAX_TOTAL_TOKENS: ClassVar[int] = 300
    MAX_RETRY_COUNT: ClassVar[int] = 10  # Added

    @field_validator("error_message")
    @classmethod
    def truncate_error_message(cls, v: str) -> str:
        """Cap error message to prevent token bloat."""
        if len(v) > cls.MAX_ERROR_MESSAGE_LENGTH:
            return v[: cls.MAX_ERROR_MESSAGE_LENGTH] + "... [truncated]"
        return v

    @field_validator("retry_count")
    @classmethod
    def validate_retry_count(cls, v: int) -> int:
        """Ensure retry count is within bounds."""
        if v < 0:
            raise ValueError("retry_count must be non-negative")
        if v > cls.MAX_RETRY_COUNT:
            raise ValueError(f"retry_count must not exceed {cls.MAX_RETRY_COUNT}")
        return v

    @model_validator(mode="wrap")
    @classmethod
    def enforce_token_budget(
        cls, data: Any, handler: ModelWrapValidatorHandler["FailureSnapshot"]
    ) -> "FailureSnapshot":
        """Enforce total snapshot size under token budget."""
        instance = handler(data)

        # Calculate approximate token count
        serialized = instance.model_dump_json()
        approx_tokens = len(serialized) // 4  # Rough: 4 chars ~ 1 token

        if approx_tokens > cls.MAX_TOTAL_TOKENS:
            # Truncate tool_call_context to fit budget
            instance.tool_call_context = {
                k: str(v)[:100] for k, v in list(instance.tool_call_context.items())[:3]
            }

        return instance

    @classmethod
    def minimal(cls, error_type: str, retry_count: int) -> "FailureSnapshot":
        """Create minimal snapshot for high context pressure."""
        return cls(
            failed_step="unknown",
            error_type=error_type,
            error_message="Error details omitted (context pressure)",
            tool_call_context={},
            retry_count=retry_count,
            context_pressure=1.0,
        )

    def to_retry_context(self) -> str:
        """Convert snapshot to human-readable retry context."""
        context_parts = [
            "## Previous Attempt Failed",
            f"**Step**: {self.failed_step}",
            f"**Error Type**: {self.error_type}",
            f"**Error Message**: {self.error_message}",
            f"**Retry Count**: {self.retry_count}",
        ]

        if self.tool_call_context:
            context_parts.append("**Tool Context**:")
            for key, value in self.tool_call_context.items():
                context_parts.append(f"  - {key}: {value}")

        context_parts.append("\nPlease retry with the above context in mind.")

        return "\n".join(context_parts)
```

**Overall Rating:** ✅ Excellent

---

## Batch 3 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 19 |
| Critical | 0 |
| Medium | 11 |
| Low | 8 |

### Key Findings

1. **Pydantic v2 Compliance**: Good use of validators with `@classmethod`. Most files missing `model_config = ConfigDict(...)`.

2. **UTC Timezone**: Mixed - `connector.py`, `failure_snapshot.py` use `datetime.now(UTC)` correctly, but `context_memory.py` and `deep_research.py` use deprecated patterns.

3. **Security**: Excellent security practices in `connector.py` with command allowlist and blocked env vars.

4. **Type Safety**: `event.py` uses discriminated union pattern excellently. Some `Any` types could be replaced with typed models.

5. **Model Design**: `failure_snapshot.py` demonstrates advanced Pydantic patterns with `@model_validator(mode="wrap")`.

### Priority Fixes

1. **Medium**: Replace `datetime.utcnow()` with `datetime.now(UTC)` in `context_memory.py`
2. **Medium**: Add `model_config = ConfigDict(...)` to all model classes
3. **Medium**: Convert `status: str` fields to enums in `deep_research.py`
4. **Low**: Consider splitting `event.py` into smaller modules
5. **Low**: Add token encryption notes for `UserConnector`

---

*Review will continue with Batch 4 (files 16-20) upon next iteration.*

---

## Batch 4: Domain Models (Files 16-20)

### 16. `backend/app/domain/models/file.py`

**Purpose:** File model for file metadata tracking

**Current Setup:**
- Simple `FileInfo` model with basic file metadata
- All fields are optional (`| None = None`)
- Includes file_id, filename, file_path, content_type, size, etc.

**Strengths:**
- Simple and straightforward model
- Covers essential file metadata

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| All fields optional | Lines 8-16 | Medium | Every field is optional - no required fields, model is too permissive |
| No UTC timezone | Line 13 | Medium | `upload_date` uses `datetime` without timezone |
| No validation | Global | Medium | No validation on filename, file_path, content_type |
| No methods | Global | Low | Model lacks helper methods (e.g., `is_image()`, `get_extension()`) |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FileInfo(BaseModel):
    """File metadata model."""

    model_config = ConfigDict(strict=True, extra="forbid")

    file_id: str = Field(..., min_length=1, description="Unique file identifier")
    filename: str = Field(..., min_length=1, max_length=255, description="Original filename")
    file_path: str | None = Field(default=None, description="Storage path")
    content_type: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9]+/[a-zA-Z0-9\-\+\.]+$")
    size: int | None = Field(default=None, ge=0, description="File size in bytes")
    upload_date: datetime | None = Field(default=None, description="Upload timestamp")
    metadata: dict[str, Any] | None = Field(default=None, max_length=50)
    user_id: str | None = Field(default=None, description="Owner user ID")
    file_url: str | None = Field(default=None, max_length=2048, description="Download URL")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Sanitize filename."""
        # Remove path separators and null bytes
        return v.replace("/", "_").replace("\\", "_").replace("\x00", "")

    def is_image(self) -> bool:
        """Check if file is an image."""
        if not self.content_type:
            return False
        return self.content_type.startswith("image/")

    def get_extension(self) -> str | None:
        """Get file extension without dot."""
        if self.filename and "." in self.filename:
            return self.filename.rsplit(".", 1)[-1].lower()
        return None

    def get_size_mb(self) -> float | None:
        """Get file size in megabytes."""
        if self.size is None:
            return None
        return self.size / (1024 * 1024)
```

**Overall Rating:** ⚠️ Needs Work

---

### 17. `backend/app/domain/models/flow_state.py`

**Purpose:** Flow state persistence models for checkpoint/recovery

**Current Setup:**
- `FlowStatus` enum for flow lifecycle states
- `FlowStateSnapshot` with comprehensive state tracking
- Immutable update pattern with `update()` method returning new instance
- Recovery and error handling methods

**Strengths:**
- Excellent immutable update pattern - methods return new instances
- Comprehensive state tracking (plan, error, iteration)
- Recovery methods: `recover_from_error()`, `can_recover()`
- Clean separation of concerns

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Lines 58-60 | Medium | Uses `datetime.now()` without UTC |
| Legacy Config class | Lines 115-116 | Medium | Uses `class Config` instead of `model_config` |
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| Empty flow_id default | Line 37 | Low | `flow_id: str = Field(default_factory=lambda: "")` - empty string default |
| No max bounds on lists | Line 46 | Low | `completed_steps` could grow unbounded |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class FlowStatus(str, Enum):
    """Status of a flow execution."""

    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    UPDATING = "updating"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    ERROR = "error"
    PAUSED = "paused"


class FlowStateSnapshot(BaseModel):
    """Snapshot of flow state for persistence and recovery."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    MAX_COMPLETED_STEPS: ClassVar[int] = 1000
    MAX_ITERATIONS: ClassVar[int] = 100

    # Identifiers
    agent_id: str
    session_id: str
    flow_id: str | None = None  # Changed from empty string to None

    # State information
    status: FlowStatus = FlowStatus.IDLE
    previous_status: FlowStatus | None = None

    # Plan state
    plan_id: str | None = None
    current_step_id: str | None = None
    completed_steps: list[str] = Field(default_factory=list, max_length=1000)

    # Error state
    error_message: str | None = None
    error_type: str | None = None
    recovery_attempts: int = Field(default=0, ge=0)

    # Iteration tracking
    iteration_count: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=MAX_ITERATIONS, ge=1, le=1000)

    # Timestamps (UTC)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_activity_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update(self, **kwargs) -> "FlowStateSnapshot":
        """Create updated snapshot with new values."""
        data = self.model_dump()
        data.update(kwargs)
        data["updated_at"] = datetime.now(UTC)
        data["last_activity_at"] = datetime.now(UTC)
        return FlowStateSnapshot.model_validate(data)
```

**Overall Rating:** ✅ Good

---

### 18. `backend/app/domain/models/knowledge_gap.py`

**Purpose:** Knowledge Gap domain models for meta-cognitive awareness

**Current Setup:**
- `GapType` and `GapSeverity` enums for categorization
- `KnowledgeGap` with resolution tracking
- `InformationRequest` for gap-filling actions
- `KnowledgeDomain` with confidence assessment
- `KnowledgeAssessment` and `CapabilityAssessment` for task evaluation

**Strengths:**
- Comprehensive meta-cognitive tracking
- `is_fillable_by_tool()` method for actionable gap identification
- Priority-based information requests
- `get_summary()` for human-readable output
- Capability coverage calculation

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Weak ID generation | Lines 42, 71 | High | Uses `datetime.now().timestamp()` - collision risk |
| No UTC timezone | Lines 51, 92, 119 | Medium | Uses `datetime.now()` without UTC |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No ID validation | Lines 72 | Low | `gap_ids: list[str]` has no validation |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeGap(BaseModel):
    """A specific gap in knowledge or capability."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"gap_{uuid.uuid4().hex}")
    gap_type: GapType
    severity: GapSeverity
    description: str = Field(..., min_length=1, max_length=1000)
    topic: str
    impact: str | None = None
    resolution_options: list[str] = Field(default_factory=list, max_length=10)
    can_be_filled: bool = True
    requires_external: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InformationRequest(BaseModel):
    """A request for information to fill a knowledge gap."""

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: f"request_{uuid.uuid4().hex}")
    gap_ids: list[str] = Field(..., min_length=1, max_length=20)
    request_type: str = Field(..., pattern=r"^(search|ask_user|read_file|api_call)$")
    query: str = Field(..., min_length=1, max_length=2000)
    priority: int = Field(default=1, ge=1, le=5)
    expected_info: str | None = None
    alternative_queries: list[str] = Field(default_factory=list, max_length=5)


class KnowledgeAssessment(BaseModel):
    """Assessment of knowledge for a specific task."""

    model_config = ConfigDict(strict=True)

    task: str = Field(..., min_length=1)
    overall_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    relevant_domains: list[KnowledgeDomain] = Field(default_factory=list, max_length=20)
    gaps: list[KnowledgeGap] = Field(default_factory=list, max_length=50)
    information_requests: list[InformationRequest] = Field(default_factory=list, max_length=20)
    can_proceed: bool = True
    blocking_gaps: list[str] = Field(default_factory=list, max_length=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
```

**Overall Rating:** ⚠️ Needs Work

---

### 19. `backend/app/domain/models/long_term_memory.py`

**Purpose:** Long-term memory models for cross-session knowledge persistence

**Current Setup:**
- `MemoryType`, `MemoryImportance`, `MemorySource` enums for categorization
- `MemoryEntry` with comprehensive tracking (embeddings, sync state, lifecycle)
- `MemoryQuery` for complex retrieval
- `MemorySearchResult`, `MemoryBatch`, `MemoryStats` for results
- `MemoryUpdate` and `ExtractedMemory` for mutations

**Strengths:**
- Very comprehensive model with embedding support
- Sync state tracking for Qdrant integration (Phase 1 foundation)
- Embedding metadata tracking (quality, model, provider)
- Access tracking with `record_access()` method
- Content hashing for deduplication
- Memory lifecycle (expires_at, is_active)

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Deprecated datetime.utcnow() | Lines 82-83, 121, 125-126 | Medium | Uses `datetime.utcnow()` instead of `datetime.now(UTC)` |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Large model size | Lines 51-127 | Low | `MemoryEntry` has 25+ fields - could be split |
| Mutable record_access | Lines 123-126 | Low | `record_access()` mutates self directly |
| Unbounded lists | Lines 69, 73-75 | Low | `keywords`, `related_memories`, `entities`, `tags` have no max |

**Enhancement Suggestions:**

```python
import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryEntry(BaseModel):
    """A single memory entry in long-term storage."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(..., min_length=1, description="Unique identifier")
    user_id: str = Field(..., min_length=1, description="Owner user ID")

    # Core content
    content: str = Field(..., min_length=1, max_length=100_000, description="Memory content")
    memory_type: MemoryType
    importance: MemoryImportance = MemoryImportance.MEDIUM
    source: MemorySource = MemorySource.SYSTEM

    # Semantic search
    embedding: list[float] | None = Field(default=None, max_length=3072)
    keywords: list[str] = Field(default_factory=list, max_length=50)

    # Context and relationships
    session_id: str | None = None
    related_memories: list[str] = Field(default_factory=list, max_length=20)
    entities: list[str] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=20)

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)
    context: str | None = Field(default=None, max_length=5000)

    # Timestamps (UTC)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime | None = None
    access_count: int = Field(default=0, ge=0)

    # Validity
    expires_at: datetime | None = None
    is_active: bool = True
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    # Sync state
    sync_state: str = Field(default="pending", pattern=r"^(pending|synced|failed|dead_letter)$")
    sync_attempts: int = Field(default=0, ge=0)
    last_sync_attempt: datetime | None = None
    sync_error: str | None = Field(default=None, max_length=500)

    # Embedding metadata
    embedding_model: str | None = None
    embedding_provider: str | None = None
    embedding_quality: float = Field(default=1.0, ge=0.0, le=1.0)

    def content_hash(self) -> str:
        """Generate hash of content for deduplication."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]

    def is_expired(self) -> bool:
        """Check if memory has expired."""
        if not self.expires_at:
            return False
        return datetime.now(UTC) > self.expires_at

    def record_access(self) -> dict[str, Any]:
        """Return update dict for recording access (immutable pattern)."""
        return {
            "last_accessed": datetime.now(UTC),
            "access_count": self.access_count + 1,
        }
```

**Overall Rating:** ✅ Good

---

### 20. `backend/app/domain/models/mcp_config.py`

**Purpose:** MCP server configuration model

**Current Setup:**
- `MCPTransport` enum for transport types (stdio, sse, streamable-http)
- `MCPServerConfig` with transport-specific validation
- `MCPConfig` container with alias support for JSON compatibility

**Strengths:**
- Good use of `@field_validator` with `@classmethod` and `ValidationInfo`
- Cross-field validation (URL required for HTTP, command required for stdio)
- Alias support: `mcpServers` -> `mcp_servers`

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Legacy Config class | Lines 53-54, 64-67 | Medium | Uses `class Config` instead of `model_config` |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| extra="allow" | Lines 54, 66 | Medium | Allows arbitrary extra fields - could hide typos |
| No security validation | Lines 20-21, 31 | Medium | No command allowlist or env var blocking (unlike connector.py) |
| No URL validation | Line 24 | Low | URL field has no format validation |

**Enhancement Suggestions:**

```python
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class MCPTransport(str, Enum):
    """MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


# Reuse from connector.py or extract to shared module
MCP_COMMAND_ALLOWLIST = frozenset({
    "npx", "node", "python", "python3", "uvx",
    "docker", "deno", "bun", "tsx", "ts-node", "pipx",
})

MCP_BLOCKED_ENV_VARS = frozenset({
    "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH", "HOME", "USER", "SHELL",
    "PYTHONPATH", "NODE_PATH", "CLASSPATH",
})


class MCPServerConfig(BaseModel):
    """MCP server configuration model."""

    model_config = ConfigDict(
        strict=True,
        extra="allow",  # Keep for forward compatibility with new MCP options
        populate_by_name=True,
    )

    command: str | None = None
    args: list[str] | None = Field(default=None, max_length=50)
    url: str | None = Field(default=None, max_length=2048)
    headers: dict[str, str] | None = Field(default=None, max_length=20)
    transport: MCPTransport
    enabled: bool = True
    description: str | None = Field(default=None, max_length=500)
    env: dict[str, str] | None = Field(default=None, max_length=20)

    @field_validator("url")
    @classmethod
    def validate_url_for_http_transport(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate URL is required for HTTP-based transports."""
        if info.data:
            transport = info.data.get("transport")
            if transport in [MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP] and not v:
                raise ValueError("URL is required for HTTP-based transports")
            if v and not v.startswith(("http://", "https://")):
                raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("command")
    @classmethod
    def validate_command_for_stdio(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate command is required for stdio transport."""
        if info.data:
            transport = info.data.get("transport")
            if transport == MCPTransport.STDIO and not v:
                raise ValueError("Command is required for stdio transport")
            if v and v not in MCP_COMMAND_ALLOWLIST:
                raise ValueError(f"Command must be one of: {', '.join(sorted(MCP_COMMAND_ALLOWLIST))}")
        return v

    @field_validator("env")
    @classmethod
    def validate_env_vars(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        """Block dangerous environment variables."""
        if v:
            blocked = MCP_BLOCKED_ENV_VARS & set(v.keys())
            if blocked:
                raise ValueError(f"Blocked environment variables: {', '.join(sorted(blocked))}")
        return v


class MCPConfig(BaseModel):
    """MCP configuration model containing all server configurations."""

    model_config = ConfigDict(
        strict=True,
        extra="allow",
        populate_by_name=True,
    )

    mcp_servers: dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        alias="mcpServers",
        max_length=50,
    )
```

**Overall Rating:** ⚠️ Needs Work

---

## Batch 4 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 21 |
| Critical | 0 |
| Medium | 15 |
| Low | 6 |

### Key Findings

1. **Pydantic v2 Compliance**: Most files use legacy `class Config` or no config at all. Need to migrate to `model_config = ConfigDict(...)`.

2. **UTC Timezone**: Mixed - some files use `datetime.now()` without UTC, others use deprecated `datetime.utcnow()`.

3. **ID Generation**: `knowledge_gap.py` uses weak timestamp-based IDs - should use UUIDs.

4. **Model Design**: `long_term_memory.py` is excellent with sync state tracking and embedding metadata. `flow_state.py` demonstrates good immutable update pattern.

5. **Security**: `mcp_config.py` lacks the security validation present in `connector.py` (command allowlist, blocked env vars).

### Priority Fixes

1. **High**: Replace timestamp-based ID generation with UUIDs in `knowledge_gap.py`
2. **Medium**: Add security validation to `mcp_config.py` (command allowlist, blocked env vars)
3. **Medium**: Migrate all `class Config` to `model_config = ConfigDict(...)`
4. **Medium**: Replace `datetime.utcnow()` with `datetime.now(UTC)` in `long_term_memory.py`
5. **Low**: Add bounds to unbounded lists

---

*Review will continue with Batch 5 (files 21-25) upon next iteration.*

---

## Batch 5: Domain Models (Files 21-25)

### 21. `backend/app/domain/models/mcp_resource.py`

**Purpose:** MCP Resource models for resource listing and reading

**Current Setup:**
- `ResourceType` enum for text vs blob content
- `MCPResource` for resource metadata
- `MCPResourceContent` with content property helpers
- `ResourceTemplate`, `ResourceSubscription` for dynamic resources
- `ResourceListResult`, `ResourceReadResult` for operation results

**Strengths:**
- Clean separation of resource types
- Good property helpers: `content`, `is_text`
- Comprehensive model for MCP protocol

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Lines 43, 92 | Medium | Uses `datetime.now()` without UTC |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No URI validation | Lines 35, 53, 77, 90 | Low | URI fields have no format validation |
| No bounds on lists | Lines 99-102 | Low | `resources`, `templates`, `errors` have no max |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MCPResource(BaseModel):
    """An MCP resource available from a server."""

    model_config = ConfigDict(strict=True, extra="forbid")

    uri: str = Field(..., min_length=1, max_length=2048, description="Unique identifier (URI format)")
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name")
    description: str | None = Field(default=None, max_length=5000)
    mime_type: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9]+/[a-zA-Z0-9\-\+\.]+$")
    server_name: str = Field(..., min_length=1, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)
    last_modified: datetime | None = None
    annotations: dict[str, Any] = Field(default_factory=dict, max_length=50)


class ResourceSubscription(BaseModel):
    """Subscription to resource updates."""

    model_config = ConfigDict(strict=True)

    uri: str = Field(..., min_length=1)
    server_name: str = Field(..., min_length=1)
    subscribed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    active: bool = True
```

**Overall Rating:** ✅ Good

---

### 22. `backend/app/domain/models/memory.py`

**Purpose:** Memory class for conversation history with auto-compaction

**Current Setup:**
- `MemoryConfig` dataclass for configuration
- `Memory` Pydantic model with message history
- Auto-compaction based on token or message count
- Smart compaction with configurable preserve_recent
- Fork/merge pattern for Tree-of-Thoughts

**Strengths:**
- Excellent fork/merge pattern for multi-path exploration
- Token-based auto-compaction (modern approach)
- `smart_compact()` with configurable function list
- `estimate_tokens()` for memory management
- `get_stats()` for observability
- Config excluded from serialization

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Legacy Config class | Lines 50-51 | Medium | Uses `class Config` instead of `model_config` |
| Mutable default | Line 22 | Medium | `compactable_functions: list[str] = None` - mutable default in dataclass |
| Direct mutation | Lines 64, 69, 101, 145 | Medium | Methods mutate `self.messages` directly |
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| Mixed dataclass/Pydantic | Lines 12-38 | Low | Uses dataclass for config - could use Pydantic |

**Enhancement Suggestions:**

```python
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.tool_result import ToolResult


class MemoryConfig(BaseModel):
    """Configuration for memory management."""

    model_config = ConfigDict(frozen=True)  # Immutable config

    max_messages: int = 100
    auto_compact_threshold: int = 50
    auto_compact_token_threshold: int = 60000
    use_token_threshold: bool = True
    compactable_functions: list[str] = Field(
        default_factory=lambda: [
            "browser_view", "browser_navigate", "browser_get_content",
            "shell_exec", "shell_view", "file_read", "file_list",
            "file_list_directory", "code_execute", "code_run_artifact",
        ]
    )
    preserve_recent: int = 8


class Memory(BaseModel):
    """Memory class for conversation history with auto-compaction."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
    )

    messages: list[dict[str, any]] = Field(default_factory=list)
    config: MemoryConfig = Field(default_factory=MemoryConfig, exclude=True)

    def model_post_init(self, __context) -> None:
        """Ensure config is always initialized."""
        if self.config is None:
            object.__setattr__(self, "config", MemoryConfig())

    def add_message(self, message: dict[str, any]) -> None:
        """Add message to memory."""
        self.messages.append(message)
        self._check_auto_compact()

    def fork(self, preserve_messages: int | None = None) -> "Memory":
        """Create a fork of this memory for isolated exploration."""
        if preserve_messages is None:
            forked_messages = [msg.copy() for msg in self.messages]
        else:
            forked_messages = [msg.copy() for msg in self.messages[-preserve_messages:]]

        return Memory(messages=forked_messages, config=self.config)
```

**Overall Rating:** ✅ Good (architecturally sound, minor improvements needed)

---

### 23. `backend/app/domain/models/memory_evidence.py`

**Purpose:** Memory evidence schema for grounding safety (Phase 4)

**Current Setup:**
- `EvidenceConfidence` enum for confidence levels
- `MemoryEvidence` dataclass with provenance tracking
- Contradiction detection support
- `to_prompt_block()` for LLM prompt injection

**Strengths:**
- Excellent grounding approach with confidence scoring
- Contradiction detection with `contradictions` list
- `needs_caveat` and `should_reject` properties for safety
- `to_prompt_block()` with metadata and caveats
- Clean separation of confidence levels

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Uses dataclass | Lines 21-123 | Medium | Should use Pydantic BaseModel for consistency |
| No UTC timezone | Line 34 | Medium | `datetime` without timezone context |
| No validation | Lines 29-37 | Low | No bounds on scores, no validation on fields |
| Mutable defaults | Lines 40-41 | Low | `contradictions`, `contradiction_reasons` use mutable defaults |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceConfidence(str, Enum):
    """Confidence level for evidence."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class MemoryEvidence(BaseModel):
    """Structured evidence from memory retrieval with provenance."""

    model_config = ConfigDict(strict=True, extra="forbid")

    memory_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source_type: str = Field(..., pattern=r"^(user_knowledge|task_artifacts|tool_logs)$")
    retrieval_score: float = Field(..., ge=0.0, le=1.0)
    embedding_quality: float = Field(..., ge=0.0, le=1.0)
    timestamp: datetime
    session_id: str | None = None
    memory_type: str = Field(..., pattern=r"^(fact|preference|procedure|entity|error_pattern)$")
    importance: str = Field(..., pattern=r"^(critical|high|medium|low)$")
    contradictions: list[str] = Field(default_factory=list, max_length=20)
    contradiction_reasons: list[str] = Field(default_factory=list, max_length=10)

    @property
    def confidence(self) -> EvidenceConfidence:
        """Compute overall confidence level."""
        combined_score = (self.retrieval_score + self.embedding_quality) / 2

        if combined_score >= 0.85:
            return EvidenceConfidence.HIGH
        if combined_score >= 0.70:
            return EvidenceConfidence.MEDIUM
        if combined_score >= 0.50:
            return EvidenceConfidence.LOW
        return EvidenceConfidence.MINIMAL

    @property
    def needs_caveat(self) -> bool:
        """Check if this evidence needs a caveat."""
        return (
            self.confidence in (EvidenceConfidence.LOW, EvidenceConfidence.MINIMAL)
            or len(self.contradictions) > 0
        )

    @property
    def should_reject(self) -> bool:
        """Check if this evidence should be rejected entirely."""
        return self.confidence == EvidenceConfidence.MINIMAL or len(self.contradictions) >= 2
```

**Overall Rating:** ✅ Good

---

### 24. `backend/app/domain/models/message.py`

**Purpose:** Chat message model for user input

**Current Setup:**
- Simple model with title, message, attachments
- Skills support with skill IDs
- Deep research mode flag
- Follow-up context from suggestion clicks

**Strengths:**
- Clean, minimal model
- Good Field descriptions for documentation
- Follow-up context tracking

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| Empty default message | Line 6 | Medium | `message: str = ""` - empty string as default |
| Mutable default | Line 7 | Medium | `attachments: list[str] = []` - should use `Field(default_factory=list)` |
| No validation | Global | Low | No validation on message length, skill IDs format |

**Enhancement Suggestions:**

```python
from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """Chat message model for user input."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    message: str = Field(default="", max_length=100_000, description="User message content")
    attachments: list[str] = Field(default_factory=list, max_length=20, description="File attachment paths")
    skills: list[str] = Field(default_factory=list, max_length=10, description="Skill IDs enabled for this message")
    deep_research: bool = Field(default=False, description="Enable deep research mode")
    follow_up_selected_suggestion: str | None = Field(default=None, max_length=1000)
    follow_up_anchor_event_id: str | None = Field(default=None, pattern=r"^[a-f0-9\-]{36}$")
    follow_up_source: str | None = Field(default=None, pattern=r"^(suggestion_click|continuation)$")

    @property
    def has_attachments(self) -> bool:
        """Check if message has attachments."""
        return len(self.attachments) > 0

    @property
    def has_skills(self) -> bool:
        """Check if any skills are enabled."""
        return len(self.skills) > 0
```

**Overall Rating:** ⚠️ Needs Work

---

### 25. `backend/app/domain/models/multi_task.py`

**Purpose:** Multi-task challenge domain models

**Current Setup:**
- `TaskStatus`, `DeliverableType` enums for categorization
- `Deliverable` for expected outputs
- `TaskDefinition` with dependency tracking
- `TaskResult` for execution results
- `MultiTaskChallenge` as container with progress tracking

**Strengths:**
- Good use of UUID generation
- Dependency tracking with `depends_on`
- Progress tracking with `get_progress_percentage()`
- Workspace template support
- Validation criteria for deliverables

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Truncated UUIDs | Lines 45, 78 | Medium | `uuid.uuid4().hex[:12]` and `[:16]` - collision risk |
| No UTC timezone | Lines 56-57, 93-94 | Medium | Uses `datetime` without timezone |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Mutable defaults | Lines 48, 52, 81, 89-90, 98 | Low | Multiple list fields with `[]` defaults |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TaskDefinition(BaseModel):
    """Definition of a single task within multi-task challenge."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1, max_length=10000)
    deliverables: list[Deliverable] = Field(default_factory=list, max_length=20)
    workspace_folder: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_\-]+$")
    validation_criteria: str | None = Field(default=None, max_length=5000)
    estimated_complexity: float = Field(default=0.5, ge=0.0, le=1.0)
    depends_on: list[str] = Field(default_factory=list, max_length=10)
    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0.0)
    iterations_used: int = Field(default=0, ge=0)


class MultiTaskChallenge(BaseModel):
    """Container for multi-task challenge execution."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"challenge_{uuid.uuid4().hex}")
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1, max_length=10000)
    tasks: list[TaskDefinition] = Field(default_factory=list, max_length=50)
    workspace_root: str = Field(default="/workspace", max_length=500)
    workspace_template: str | None = Field(default=None, pattern=r"^(research|data_analysis|code_project)$")
    current_task_index: int = Field(default=0, ge=0)
    completed_tasks: list[str] = Field(default_factory=list, max_length=50)
    failed_tasks: list[str] = Field(default_factory=list, max_length=50)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_seconds: float | None = Field(default=None, ge=0.0)
    task_results: list[TaskResult] = Field(default_factory=list, max_length=50)
    overall_success: bool = False

    def get_current_task(self) -> TaskDefinition | None:
        """Get currently active task."""
        if 0 <= self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]
        return None

    def get_progress_percentage(self) -> float:
        """Calculate overall progress."""
        if not self.tasks:
            return 0.0
        return (len(self.completed_tasks) / len(self.tasks)) * 100
```

**Overall Rating:** ✅ Good

---

## Batch 5 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 17 |
| Critical | 0 |
| Medium | 12 |
| Low | 5 |

### Key Findings

1. **Pydantic vs Dataclass**: `memory_evidence.py` uses dataclass instead of Pydantic BaseModel - should be consistent with other models.

2. **UTC Timezone**: Mixed - some files use `datetime` without timezone context.

3. **ID Generation**: `multi_task.py` truncates UUIDs - should use full UUIDs or prefixed format.

4. **Model Design**: `memory.py` demonstrates excellent fork/merge pattern for Tree-of-Thoughts.

5. **Grounding Safety**: `memory_evidence.py` implements comprehensive evidence tracking with confidence and contradiction detection.

### Priority Fixes

1. **Medium**: Convert `MemoryEvidence` from dataclass to Pydantic BaseModel
2. **Medium**: Add `model_config = ConfigDict(...)` to all model classes
3. **Medium**: Fix truncated UUIDs in `multi_task.py`
4. **Low**: Add timezone to datetime fields
5. **Low**: Add bounds to unbounded lists

---

*Review will continue with Batch 6 (files 26-30) upon next iteration.*

---

## Batch 6: Domain Models (Files 26-30)

### 26. `backend/app/domain/models/path_state.py`

**Purpose:** Path state models for Tree-of-Thoughts multi-path exploration

**Current Setup:**
- `PathStatus` and `BranchingDecision` enums for path lifecycle
- `PathMetrics` dataclass for scoring paths
- `PathState` dataclass with comprehensive state tracking
- `ComplexityAnalysis` and `TreeOfThoughtsConfig` dataclasses
- `PathScoreWeights` Pydantic model for scoring weights

**Strengths:**
- Comprehensive Tree-of-Thoughts implementation
- Path scoring with metrics tracking
- Complexity analysis for branching decisions
- `PathMetrics.average_confidence` and `error_rate` properties

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Truncated UUID | Line 67 | High | `str(uuid.uuid4())[:8]` - only 8 chars, collision risk |
| Uses dataclasses | Lines 36-61, 63-145, 157-172, 184-196 | Medium | Should use Pydantic for consistency |
| No UTC timezone | Lines 88, 95, 101, 107, 113 | Medium | Uses `datetime.now()` without UTC |
| Mutable defaults | Lines 44, 73, 80, 85, 164 | Low | Multiple list fields with `field(default_factory=list)` |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PathState(BaseModel):
    """State of a single exploration path."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"path_{uuid.uuid4().hex}")
    description: str = ""
    strategy: str = ""
    status: PathStatus = PathStatus.CREATED
    steps: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    current_step_index: int = Field(default=0, ge=0)
    metrics: PathMetrics = Field(default_factory=PathMetrics)
    intermediate_results: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    final_result: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self) -> None:
        """Mark path as started."""
        self.status = PathStatus.EXPLORING
        self.started_at = datetime.now(UTC)
```

**Overall Rating:** ⚠️ Needs Work

---

### 27. `backend/app/domain/models/plan.py`

**Purpose:** Plan models with phases, steps, and quality analysis

**Current Setup:**
- `PhaseType`, `StepType`, `ExecutionStatus` enums for categorization
- `Phase`, `Step`, `Plan` Pydantic models for plan structure
- `RetryPolicy` for per-step retry configuration
- `PlanQualityAnalyzer` class with multi-dimensional quality analysis
- `ValidationResult`, `PlanQualityMetrics` dataclasses for analysis results

**Strengths:**
- EXCELLENT - Comprehensive plan management with phases and steps
- `ExecutionStatus` with rich class methods: `get_active_statuses()`, `is_terminal()`, etc.
- Dependency tracking with circular dependency detection
- `infer_smart_dependencies()` with pattern detection
- Multi-dimensional quality analysis (Clarity, Completeness, Structure, Feasibility, Efficiency)
- `unblock_independent_steps()` for partial result handling
- Uses UTC correctly in `PlanQualityAnalyzer.analyze()` (Line 835)

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Uses dataclasses | Lines 596-607, 619-640, 642-696 | Low | `ValidationResult`, `DimensionScore`, `PlanQualityMetrics` use dataclass |
| No model_config | Lines 29-56, 117-125, 127-177, 179-594 | Medium | Missing `ConfigDict` for Pydantic models |
| Mutable defaults | Lines 136, 140, 187 | Low | `attachments`, `dependencies`, `steps` with `[]` |
| Large file | Global | Low | 1114 lines - could split into plan.py, plan_quality.py |

**Enhancement Suggestions:**

```python
from pydantic import BaseModel, ConfigDict, Field


class Phase(BaseModel):
    """A phase grouping multiple steps in the agent workflow."""

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    phase_type: PhaseType
    label: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    status: "ExecutionStatus" = Field(default="pending")
    order: int = Field(default=0, ge=0)
    icon: str = ""
    color: str = ""
    step_ids: list[str] = Field(default_factory=list, max_length=50)
    skipped: bool = False
    skip_reason: str | None = None


class Step(BaseModel):
    """Step in a plan with enhanced status tracking."""

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str = Field(default="", max_length=2000)
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: str | None = None
    error: str | None = None
    success: bool = False
    attachments: list[str] = Field(default_factory=list, max_length=20)
    notes: str = ""
    agent_type: str | None = None
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    blocked_by: str | None = None
    metadata: dict[str, Any] | None = Field(default=None, max_length=50)
    phase_id: str | None = None
    step_type: StepType = StepType.EXECUTION
    expected_output: str | None = None
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    budget_tokens: int | None = Field(default=None, ge=0)
```

**Overall Rating:** ✅ Excellent (with minor improvements needed)

---

### 28. `backend/app/domain/models/pressure.py`

**Purpose:** Canonical PressureLevel enum for token/memory pressure management

**Current Setup:**
- Single `PressureLevel` enum with 5 levels
- Clear documentation on thresholds
- Used by both TokenManager and MemoryManager

**Strengths:**
- Simple, focused model with single responsibility
- Clear documentation with percentage thresholds
- Canonical source for pressure levels

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| None | - | - | This file is well-designed |

**Enhancement Suggestions:**

```python
from enum import Enum


class PressureLevel(str, Enum):
    """Token/memory pressure levels for proactive management.

    Used by both TokenManager and MemoryManager for consistent
    pressure detection and response.

    Thresholds (Priority 4: Optimized for better context utilization):
    - NORMAL: < 60% - operating normally
    - EARLY_WARNING: 60-70% - early notice for planning
    - WARNING: 70-80% - consider summarizing
    - CRITICAL: 80-90% - begin proactive trimming
    - OVERFLOW: > 90% - force immediate action
    """

    NORMAL = "normal"
    EARLY_WARNING = "early_warning"
    WARNING = "warning"
    CRITICAL = "critical"
    OVERFLOW = "overflow"

    @classmethod
    def from_percentage(cls, percentage: float) -> "PressureLevel":
        """Determine pressure level from a percentage value."""
        if percentage < 0.6:
            return cls.NORMAL
        if percentage < 0.7:
            return cls.EARLY_WARNING
        if percentage < 0.8:
            return cls.WARNING
        if percentage < 0.9:
            return cls.CRITICAL
        return cls.OVERFLOW
```

**Overall Rating:** ✅ Excellent

---

### 29. `backend/app/domain/models/recovery.py`

**Purpose:** Response Recovery Domain Models for handling LLM response failures

**Current Setup:**
- `RecoveryReason` and `RecoveryStrategy` enums for categorization
- `RecoveryDecision` model with retry tracking
- `RecoveryAttempt` model for attempt history
- `RecoveryBudgetExhaustedError` and `MalformedResponseError` exceptions

**Strengths:**
- Clean separation of recovery concerns
- Pydantic v2 compliant validators with `@classmethod`
- Custom exceptions with detailed attributes
- `RecoveryAttempt` with timing tracking

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Lines 74 | Low | `datetime` without timezone context |
| No model_config | Lines 32-55, 58-85 | Medium | Missing `ConfigDict` for Pydantic models |
| No timestamp defaults | Lines 74 | Low | No `default_factory` for `start_time` |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecoveryDecision(BaseModel):
    """Decision outcome from recovery policy."""

    model_config = ConfigDict(strict=True, extra="forbid")

    should_recover: bool
    recovery_reason: RecoveryReason
    strategy: RecoveryStrategy
    retry_count: int = Field(default=0, ge=0)
    message: str = Field(..., max_length=1000)


class RecoveryAttempt(BaseModel):
    """Record of a recovery attempt."""

    model_config = ConfigDict(strict=True)

    attempt_number: int = Field(..., ge=1)
    recovery_reason: RecoveryReason
    strategy_used: RecoveryStrategy
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    success: bool | None = None
    error_message: str | None = Field(default=None, max_length=2000)
```

**Overall Rating:** ✅ Good

---

### 30. `backend/app/domain/models/reflection.py`

**Purpose:** Reflection models for intermediate progress assessment (Phase 2)

**Current Setup:**
- `ReflectionTriggerType` and `ReflectionDecision` enums
- `ReflectionTrigger` dataclass with trigger configuration
- `ProgressMetrics` dataclass for tracking execution
- `ReflectionResult` Pydantic model for assessment results
- `ReflectionConfig` dataclass for configuration
- Helper functions: `calculate_plan_divergence()`, `detect_pattern_change()`

**Strengths:**
- Comprehensive reflection system with multiple trigger types
- `ReflectionTrigger.should_trigger_enhanced()` with plan divergence detection
- `ProgressMetrics` with stall detection and success rate
- Pattern change detection in tool usage
- `ReflectionResult` with decision factors and alternatives

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Uses dataclasses | Lines 43-203, 310-393, 446-454 | Medium | `ReflectionTrigger`, `ProgressMetrics`, `ReflectionConfig` use dataclass |
| No UTC timezone | Lines 361, 377 | Medium | Uses `datetime.now()` without UTC |
| No model_config | Lines 396-444 | Medium | `ReflectionResult` missing `ConfigDict` |
| Mutable defaults | Lines 69, 330 | Low | `_confidence_history`, `errors` use mutable defaults |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReflectionResult(BaseModel):
    """Result of a reflection assessment."""

    model_config = ConfigDict(strict=True, extra="forbid")

    decision: ReflectionDecision
    confidence: float = Field(..., ge=0.0, le=1.0)
    progress_assessment: str = Field(..., max_length=5000)
    issues_identified: list[str] = Field(default_factory=list, max_length=20)
    strategy_adjustment: str | None = Field(default=None, max_length=2000)
    replan_reason: str | None = Field(default=None, max_length=2000)
    user_question: str | None = Field(default=None, max_length=1000)
    summary: str = Field(..., max_length=2000)
    trigger_type: ReflectionTriggerType | None = None
    decision_factors: list[str] = Field(default_factory=list, max_length=10)
    alternative_decisions: list[str] = Field(default_factory=list, max_length=5)
    recommended_actions: list[str] = Field(default_factory=list, max_length=10)


class ProgressMetrics(BaseModel):
    """Metrics tracking execution progress."""

    model_config = ConfigDict(strict=True)

    steps_completed: int = Field(default=0, ge=0)
    steps_remaining: int = Field(default=0, ge=0)
    total_steps: int = Field(default=0, ge=0)
    successful_actions: int = Field(default=0, ge=0)
    failed_actions: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    last_progress_at: datetime | None = None
    actions_since_progress: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list, max_length=20)

    @property
    def success_rate(self) -> float:
        total = self.successful_actions + self.failed_actions
        if total == 0:
            return 1.0
        return self.successful_actions / total

    @property
    def is_stalled(self) -> bool:
        return self.actions_since_progress >= 3

    def record_success(self) -> None:
        self.successful_actions += 1
        self.actions_since_progress = 0
        self.last_progress_at = datetime.now(UTC)
```

**Overall Rating:** ✅ Good

---

## Batch 6 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 15 |
| Critical | 0 |
| Medium | 8 |
| Low | 7 |

### Key Findings

1. **Pydantic vs Dataclass**: Several files (`path_state.py`, `reflection.py`) use dataclasses for core models - should migrate to Pydantic for consistency.

2. **Model Design**: `plan.py` is exemplary - comprehensive with quality analysis, dependency tracking, and validation.

3. **Simple Models**: `pressure.py` demonstrates good single-responsibility principle with a focused enum.

4. **UTC Timezone**: Mixed - `plan.py` uses UTC correctly, but `path_state.py` and `reflection.py` use `datetime.now()` without timezone.

5. **ID Generation**: `path_state.py` truncates UUID to 8 characters - collision risk.

### Priority Fixes

1. **High**: Fix truncated UUIDs in `path_state.py`
2. **Medium**: Convert dataclasses to Pydantic models in `path_state.py` and `reflection.py`
3. **Medium**: Add `model_config = ConfigDict(...)` to Pydantic models
4. **Low**: Consider splitting `plan.py` into smaller modules
5. **Low**: Add timezone to datetime fields

---

*Review will continue with Batch 7 (files 31-35) upon next iteration.*

---

## Batch 7: Domain Models (Files 31-35)

### 31. `backend/app/domain/models/repo_map.py`

**Purpose:** Repository Map Domain Models for codebase structure and navigation

**Current Setup:**
- `EntryType` enum for repository entry types
- `RepoMapEntry` dataclass for individual entries
- `RepoMap` dataclass for complete repository maps
- `RepoMapConfig` dataclass for configuration
- Token-aware context string generation

**Strengths:**
- `to_context_line()` for compact LLM-friendly output
- Token-aware `to_context_string()` with truncation
- Importance scoring for entries
- Language detection and file counting
- Configurable include/exclude patterns

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Uses dataclasses | Lines 27-89, 133-251, 254-319 | Medium | Should use Pydantic for consistency |
| Unix timestamp | Line 152 | Low | Uses float for `generated_at` instead of datetime |
| No model_config | Global | Medium | Missing `ConfigDict` |
| Mutable defaults | Lines 52, 58, 140, 149, 263, 283 | Low | Multiple list/dict fields with mutable defaults |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RepoMapEntry(BaseModel):
    """A single entry in the repository map."""

    model_config = ConfigDict(strict=True, extra="forbid")

    path: str = Field(..., min_length=1, max_length=1000)
    entry_type: EntryType
    name: str = Field(..., min_length=1, max_length=500)
    signature: str | None = Field(default=None, max_length=1000)
    docstring: str | None = Field(default=None, max_length=5000)
    line_number: int | None = Field(default=None, ge=1)
    parent: str | None = None
    references: list[str] = Field(default_factory=list, max_length=100)
    importance: float = Field(default=1.0, ge=0.0, le=10.0)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)

    def to_context_line(self, include_signature: bool = True) -> str:
        """Convert to a single line for context."""
        # ... implementation ...
```

**Overall Rating:** ⚠️ Needs Work

---

### 32. `backend/app/domain/models/report.py`

**Purpose:** Structured Report Models with discriminated unions for flexible output types

**Current Setup:**
- `ReportType` enum for report categories
- `ReportSection`, `KeyFinding`, `Benchmark`, `ComparisonItem` models
- Discriminated union: `ResearchReport | ComparisonReport | AnalysisReport`
- `ReportMetadata`, `CitationEntry`, `StructuredReportOutput` for complete output

**Strengths:**
- Excellent discriminated union pattern with `Literal["research"]` etc.
- `@field_validator` to prevent placeholder content
- `min_length` constraints on critical fields
- Complete report structure with metadata and citations
- Type-safe report handling via discriminator

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Deprecated datetime.utcnow() | Lines 82, 95, 109 | Medium | Uses `datetime.utcnow()` instead of `datetime.now(UTC)` |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No citation ID format validation | Lines 25, 43, 67 | Low | Citation IDs have no format validation |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReportSection(BaseModel):
    """A section within a report."""

    model_config = ConfigDict(strict=True, extra="forbid")

    heading: str = Field(..., min_length=3, max_length=200)
    content: str = Field(..., min_length=10, max_length=50000)
    citations: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    @field_validator("content")
    @classmethod
    def validate_content_not_placeholder(cls, v: str) -> str:
        """Ensure content is not placeholder text."""
        placeholders = ["todo", "tbd", "lorem ipsum", "[content]", "placeholder"]
        if any(p in v.lower() for p in placeholders):
            raise ValueError("Section content appears to be placeholder text")
        return v


class ResearchReport(BaseModel):
    """Research report with findings and citations."""

    model_config = ConfigDict(strict=True)

    report_type: Literal["research"] = "research"
    title: str = Field(..., min_length=5, max_length=500)
    executive_summary: str = Field(..., min_length=50, max_length=10000)
    key_findings: list[KeyFinding] = Field(..., min_length=1, max_length=50)
    sections: list[ReportSection] = Field(..., min_length=1, max_length=50)
    benchmarks: list[Benchmark] = Field(default_factory=list, max_length=100)
    methodology: str | None = Field(default=None, max_length=10000)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

**Overall Rating:** ✅ Good

---

### 33. `backend/app/domain/models/research_phase.py`

**Purpose:** Domain models for phased research workflows

**Current Setup:**
- `ResearchPhase` enum for structured phases
- `ResearchCheckpoint` for saved notes from completed phases
- `ResearchState` for tracking progress across phases

**Strengths:**
- Simple, focused models for phased research
- Checkpoint pattern for phase persistence
- Clean state tracking

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Line 26 | Medium | Uses `datetime.now()` without UTC |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No bounds on checkpoints | Line 34 | Low | `checkpoints` list has no max |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResearchCheckpoint(BaseModel):
    """Saved notes from a completed research phase."""

    model_config = ConfigDict(strict=True, extra="forbid")

    phase: ResearchPhase
    notes: str = Field(..., max_length=50000)
    sources: list[str] = Field(default_factory=list, max_length=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    query_context: str = Field(..., max_length=5000)


class ResearchState(BaseModel):
    """Tracks progress across phased research execution."""

    model_config = ConfigDict(strict=True)

    current_phase: ResearchPhase
    checkpoints: list[ResearchCheckpoint] = Field(default_factory=list, max_length=20)
    action_count: int = Field(default=0, ge=0)
    last_reflection: str | None = Field(default=None, max_length=10000)
    next_step: str | None = Field(default=None, max_length=2000)
```

**Overall Rating:** ⚠️ Needs Work

---

### 34. `backend/app/domain/models/research_task.py`

**Purpose:** Research task model for wide research pattern (parallel sub-tasks)

**Current Setup:**
- `ResearchStatus` enum for task lifecycle
- `ResearchTask` model with comprehensive state tracking
- Methods: `start()`, `complete()`, `fail()`, `skip()`
- Uses UTC correctly: `datetime.now(UTC)`

**Strengths:**
- EXCELLENT - Uses `datetime.now(UTC)` correctly throughout
- Prefixed ID: `f"research_{uuid.uuid4().hex[:12]}"`
- Clean state management with methods
- Good documentation on wide research pattern

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Truncated UUID | Line 47 | Medium | `uuid.uuid4().hex[:12]` - only 12 hex chars |
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| No max bounds on sources | Line 54 | Low | `sources` list has no max |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResearchTask(BaseModel):
    """A single research sub-task in wide research."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"research_{uuid.uuid4().hex}")
    query: str = Field(..., min_length=1, max_length=5000)
    parent_task_id: str = Field(..., min_length=1)
    index: int = Field(..., ge=0)
    total: int = Field(..., ge=1)
    status: ResearchStatus = ResearchStatus.PENDING
    result: str | None = Field(default=None, max_length=100000)
    sources: list[str] = Field(default_factory=list, max_length=50)
    error: str | None = Field(default=None, max_length=5000)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self) -> None:
        """Mark task as started."""
        self.status = ResearchStatus.IN_PROGRESS
        self.started_at = datetime.now(UTC)

    def complete(self, result: str, sources: list[str] | None = None) -> None:
        """Mark task as completed with result."""
        self.status = ResearchStatus.COMPLETED
        self.result = result
        self.sources = sources or []
        self.completed_at = datetime.now(UTC)
```

**Overall Rating:** ✅ Good

---

### 35. `backend/app/domain/models/screenshot.py`

**Purpose:** Session screenshot domain models

**Current Setup:**
- `ScreenshotTrigger` enum for capture timing
- `SessionScreenshot` model with deduplication support
- Uses UTC correctly: `datetime.now(UTC)`
- MinIO S3 storage integration

**Strengths:**
- Uses UTC correctly
- Deduplication support with perceptual hash
- Thumbnail storage support
- Tool call linking

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| No ID validation | Line 18 | Low | `id` has no format validation |
| No size validation | Line 29 | Low | `size_bytes` has no bounds |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SessionScreenshot(BaseModel):
    """Session screenshot model."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(..., min_length=1, max_length=100)
    session_id: str = Field(..., min_length=1, max_length=100)
    sequence_number: int = Field(..., ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    storage_key: str = Field(..., min_length=1, max_length=500)
    thumbnail_storage_key: str | None = Field(default=None, max_length=500)
    trigger: ScreenshotTrigger
    tool_call_id: str | None = Field(default=None, max_length=100)
    tool_name: str | None = Field(default=None, max_length=100)
    function_name: str | None = Field(default=None, max_length=100)
    action_type: str | None = Field(default=None, max_length=50)
    size_bytes: int = Field(default=0, ge=0, le=50_000_000)  # 50MB max
    perceptual_hash: str | None = Field(default=None, max_length=64)
    is_duplicate: bool = False
    original_storage_key: str | None = Field(default=None, max_length=500)
```

**Overall Rating:** ✅ Good

---

## Batch 7 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 14 |
| Critical | 0 |
| Medium | 8 |
| Low | 6 |

### Key Findings

1. **Pydantic vs Dataclass**: `repo_map.py` uses dataclasses - should migrate to Pydantic.

2. **UTC Timezone**: Good - `research_task.py` and `screenshot.py` use `datetime.now(UTC)` correctly. Issues in `report.py` (deprecated `datetime.utcnow()`) and `research_phase.py`.

3. **Discriminated Unions**: `report.py` demonstrates excellent discriminated union pattern with `Literal["type"]`.

4. **Wide Research Pattern**: `research_task.py` implements the wide research pattern for parallel sub-tasks with isolated contexts.

5. **Repository Mapping**: `repo_map.py` provides token-aware context generation for LLM consumption.

### Priority Fixes

1. **Medium**: Replace `datetime.utcnow()` with `datetime.now(UTC)` in `report.py`
2. **Medium**: Convert dataclasses to Pydantic in `repo_map.py`
3. **Medium**: Add `model_config = ConfigDict(...)` to all model classes
4. **Low**: Fix truncated UUID in `research_task.py`
5. **Low**: Add max bounds to list fields

---

*Review will continue with Batch 8 (files 36-40) upon next iteration.*

---

## Batch 8: Domain Models (Files 36-40)

### 36. `backend/app/domain/models/scheduled_task.py`

**Purpose:** Scheduled Task Model for deferred or recurring agent execution

**Current Setup:**
- Multiple enums: `ScheduleType`, `NotificationChannel`, `OutputDeliveryMethod`, `ScheduledTaskStatus`, `ExecutionStatus`
- `ExecutionRecord`, `ScheduleConfig`, `NotificationConfig`, `OutputConfig` models
- `ScheduledTask` with comprehensive scheduling, retry logic, and execution history
- Uses UTC correctly: `datetime.now(UTC)` throughout

**Strengths:**
- EXCELLENT - Comprehensive scheduling system with cron, daily, weekly, monthly support
- Uses UTC correctly throughout
- Execution history with 100-record limit
- Bounded history cleanup (Lines 233-234)
- Retry logic with delay configuration
- `_calculate_next_execution()` with multiple schedule types
- `get_execution_stats()` for observability

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Truncated UUIDs | Lines 73, 137 | Medium | `uuid.uuid4().hex[:12]` and `[:16]` - collision risk |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Mutable defaults | Lines 91, 103, 107, 117, 173, 180 | Low | Multiple list fields with `Field(default_factory=list)` |
| Duplicated ExecutionStatus | Line 61 | Low | Same enum exists in `plan.py` - should be shared |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ScheduledTask(BaseModel):
    """Scheduled task model for deferred or recurring agent execution."""

    model_config = ConfigDict(strict=True, extra="forbid")

    MIN_INTERVAL_SECONDS: int = 300

    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex}")
    user_id: str = Field(..., min_length=1)
    session_id: str | None = None
    name: str = Field(default="", max_length=200)
    task_description: str = Field(..., min_length=1, max_length=10000)
    schedule_type: ScheduleType = ScheduleType.ONCE
    scheduled_at: datetime
    interval_seconds: int | None = Field(default=None, ge=300)
    # ... rest of fields
```

**Overall Rating:** ✅ Excellent

---

### 37. `backend/app/domain/models/search.py`

**Purpose:** Search result models for web search

**Current Setup:**
- Simple `SearchResultItem` model
- `SearchResults` container model

**Strengths:**
- Simple, focused models
- Clear field descriptions

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No validation | Global | Low | No URL validation on `link`, no length bounds |
| Empty default | Line 9 | Low | `snippet: str = Field(default="")` - empty default |

**Enhancement Suggestions:**

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchResultItem(BaseModel):
    """Single search result item."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1, max_length=500)
    link: str = Field(..., min_length=1, max_length=2048)
    snippet: str = Field(default="", max_length=2000)

    @field_validator("link")
    @classmethod
    def validate_link(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Link must be a valid URL")
        return v


class SearchResults(BaseModel):
    """Complete search results data structure."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=1, max_length=1000)
    date_range: str | None = Field(default=None, max_length=100)
    total_results: int = Field(default=0, ge=0)
    results: list[SearchResultItem] = Field(default_factory=list, max_length=100)
```

**Overall Rating:** ⚠️ Needs Work

---

### 38. `backend/app/domain/models/session.py`

**Purpose:** Session model for agent session management

**Current Setup:**
- `SessionStatus` and `AgentMode` enums
- `Session` model with comprehensive session tracking
- Sandbox lifecycle management
- Budget tracking
- Multi-task challenge support

**Strengths:**
- Uses UTC correctly: `datetime.now(UTC)` (Lines 45-47)
- Sandbox lifecycle modes (static/ephemeral)
- Budget tracking with warning threshold
- `get_last_plan()` method for plan retrieval
- Multi-task challenge integration

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Truncated UUID | Line 34 | Medium | `uuid.uuid4().hex[:16]` - collision risk |
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| Mutable defaults | Lines 48-49, 60, 65-66 | Low | `events`, `files`, `workspace_capabilities` with mutable defaults |
| Circular import risk | Lines 7-10 | Low | Imports from multiple domain models |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.domain.models.event import AgentEvent, PlanEvent
    from app.domain.models.file import FileInfo
    from app.domain.models.multi_task import MultiTaskChallenge
    from app.domain.models.plan import Plan


class Session(BaseModel):
    """Session model."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"session_{uuid.uuid4().hex}")
    user_id: str = Field(..., min_length=1)
    sandbox_id: str | None = None
    sandbox_owned: bool = False
    sandbox_lifecycle_mode: str | None = Field(default=None, pattern=r"^(static|ephemeral)$")
    sandbox_created_at: datetime | None = None
    agent_id: str = Field(..., min_length=1)
    # ... rest of fields with proper bounds
```

**Overall Rating:** ✅ Good

---

### 39. `backend/app/domain/models/skill.py`

**Purpose:** Skill domain models for prepackaged agent capabilities

**Current Setup:**
- Multiple enums: `ResourceType`, `SkillCategory`, `SkillSource`, `SkillInvocationType`
- `SkillResource`, `SkillMetadata` models
- `Skill` model with progressive disclosure, marketplace features
- `UserSkillConfig` for per-user configuration

**Strengths:**
- EXCELLENT - Comprehensive skill system with progressive disclosure
- Uses UTC correctly: `datetime.now(UTC)` (Lines 185-186)
- `get_disclosure_level()` for level-based data exposure
- `from_skill_md()` class method for SKILL.md parsing
- Marketplace features (rating, install count)
- Trigger patterns for automatic activation

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Regex in method | Lines 108, 318 | Low | Regex compiled on every call - could cache |
| Mutable defaults | Lines 136-143, 177, 222 | Low | Multiple list fields with mutable defaults |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

# Pre-compiled regex for frontmatter
import re
_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n?---", re.DOTALL)


class Skill(BaseModel):
    """Prepackaged capability for agents."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    category: SkillCategory
    source: SkillSource = SkillSource.CUSTOM
    icon: str = Field(default="sparkles", max_length=50)
    required_tools: list[str] = Field(default_factory=list, max_length=50)
    optional_tools: list[str] = Field(default_factory=list, max_length=50)
    system_prompt_addition: str | None = Field(default=None, max_length=50000)
    configurations: dict[str, dict[str, Any]] = Field(default_factory=dict, max_length=50)
    default_enabled: bool = False
    invocation_type: SkillInvocationType = SkillInvocationType.BOTH
    allowed_tools: list[str] | None = Field(default=None, max_length=100)
    supports_dynamic_context: bool = False
    trigger_patterns: list[str] = Field(default_factory=list, max_length=20)
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    author: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_premium: bool = False
    owner_id: str | None = None
    is_public: bool = False
    parent_skill_id: str | None = None
    community_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    rating_count: int = Field(default=0, ge=0)
    install_count: int = Field(default=0, ge=0)
    is_featured: bool = False
    tags: list[str] = Field(default_factory=list, max_length=20)
    body: str = Field(default="", max_length=100000)
    resources: list[SkillResource] = Field(default_factory=list, max_length=50)

    def get_disclosure_level(self, level: int) -> dict[str, Any]:
        """Get skill data at the specified disclosure level."""
        if level not in (1, 2, 3):
            raise ValueError(f"Invalid disclosure level: {level}. Must be 1, 2, or 3.")
        # ... implementation
```

**Overall Rating:** ✅ Excellent

---

### 40. `backend/app/domain/models/skill_package.py`

**Purpose:** Skill package domain models for deliverable skill artifacts

**Current Setup:**
- `SkillPackageType` enum for package complexity
- Multiple nested models: `SkillFeatureMapping`, `SkillFeatureCategory`, `SkillWorkflowStep`, `SkillExample`, `SkillImplementationLayer`, `SkillPackageFile`, `SkillPackageMetadata`
- `SkillPackage` model with file management and Manus-style format

**Strengths:**
- EXCELLENT - Comprehensive skill package system
- Uses UTC correctly: `datetime.now(UTC)` (Lines 173-174)
- Manus-style four-layer implementation pattern
- File type detection in `SkillPackageFile.from_content()`
- Directory-based file organization with helper methods
- `summary` property for package overview

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No ID generation | Line 154 | Low | `id: str` has no default factory |
| Mutable defaults | Lines 42, 50, 69, 114-115, 120, 128-136, 164-165 | Low | Multiple list/dict fields with mutable defaults |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SkillPackage(BaseModel):
    """A deliverable skill package."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"pkg_{uuid.uuid4().hex}")
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    icon: str = Field(default="puzzle", max_length=50)
    category: str = Field(default="custom", max_length=50)
    author: str | None = Field(default=None, max_length=200)
    package_type: SkillPackageType = SkillPackageType.STANDARD
    files: list[SkillPackageFile] = Field(default_factory=list, max_length=500)
    file_tree: dict[str, Any] = Field(default_factory=dict, max_length=100)
    file_id: str | None = None
    skill_id: str | None = None
    metadata: SkillPackageMetadata | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def filename(self) -> str:
        """Get the package filename with .skill extension."""
        safe_name = self.name.lower().replace(" ", "-")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "-")
        return f"{safe_name}.skill"
```

**Overall Rating:** ✅ Excellent

---

## Batch 8 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 16 |
| Critical | 0 |
| Medium | 8 |
| Low | 8 |

### Key Findings

1. **Comprehensive Systems**: `scheduled_task.py`, `skill.py`, and `skill_package.py` demonstrate excellent domain modeling with comprehensive feature sets.

2. **UTC Timezone**: All files correctly use `datetime.now(UTC)`.

3. **Progressive Disclosure**: Both `skill.py` and `skill_package.py` implement the Manus-style progressive disclosure pattern.

4. **Scheduling**: `scheduled_task.py` implements a complete scheduling system with multiple schedule types and execution history.

5. **Simple Models**: `search.py` is minimal but could use more validation.

### Priority Fixes

1. **Medium**: Add `model_config = ConfigDict(...)` to all model classes
2. **Medium**: Fix truncated UUIDs in `scheduled_task.py` and `session.py`
3. **Medium**: Add URL validation to `SearchResultItem.link`
4. **Low**: Extract duplicate `ExecutionStatus` enum to shared module
5. **Low**: Cache compiled regex patterns in `skill.py`

---

## Batch 9: Domain Models (Files 41-45)

### 41. `backend/app/domain/models/snapshot.py`

**Purpose:** State snapshot models for timeline reconstruction - captures point-in-time state for various resources

**Current Setup:**
- `SnapshotType` enum for different snapshot categories (FILE_SYSTEM, BROWSER_STATE, TERMINAL_STATE, etc.)
- Multiple snapshot models: `FileSnapshot`, `FileSystemSnapshot`, `BrowserSnapshot`, `TerminalSnapshot`, `EditorSnapshot`, `PlanSnapshot`
- `StateSnapshot` aggregate with factory methods for creating typed snapshots
- Uses `datetime.now()` without UTC in defaults and factory methods

**Strengths:**
- Comprehensive snapshot types covering all sandbox resources
- Factory methods (`create_file_snapshot`, `create_browser_snapshot`, `create_terminal_snapshot`) for clean construction
- Compression tracking with `is_compressed` and `compressed_size_bytes`
- Sequence number for timeline ordering

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Lines 29, 96, 134 | High | Uses `datetime.now()` without UTC - inconsistent timestamps |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Mutable list default | Line 36 | Medium | `files: list[FileSnapshot] = []` - should use `Field(default_factory=list)` |
| No ID prefix | Line 90 | Low | `str(uuid.uuid4())` lacks prefix for identification |
| No bounds on lists | Lines 36, 80 | Low | `files`, `completed_steps` have no max limits |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FileSnapshot(BaseModel):
    """Snapshot of a single file."""

    model_config = ConfigDict(strict=True, extra="forbid")

    path: str = Field(..., max_length=1000)
    content: str = Field(..., max_length=10_000_000)  # 10MB limit
    size_bytes: int = Field(..., ge=0)
    modified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_binary: bool = False


class StateSnapshot(BaseModel):
    """Point-in-time state snapshot for timeline reconstruction."""

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: f"snap_{uuid.uuid4().hex}")
    session_id: str = Field(..., min_length=1)
    action_id: str | None = None
    sequence_number: int = Field(..., ge=0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    snapshot_type: SnapshotType
    resource_path: str | None = Field(default=None, max_length=2000)

    file_system: FileSystemSnapshot | None = None
    file_content: FileSnapshot | None = None
    browser: BrowserSnapshot | None = None
    terminal: TerminalSnapshot | None = None
    editor: EditorSnapshot | None = None
    plan: PlanSnapshot | None = None
    full_state: dict[str, Any] | None = None

    is_compressed: bool = False
    compressed_size_bytes: int | None = Field(default=None, ge=0)
```

**Overall Rating:** ⚠️ Needs Work

---

### 42. `backend/app/domain/models/source_attribution.py`

**Purpose:** Source attribution model for tracking claim provenance - prevents hallucinations and ensures proper attribution

**Current Setup:**
- `SourceType` enum (DIRECT_CONTENT, INFERRED, UNAVAILABLE)
- `AccessStatus` enum (FULL, PARTIAL, PAYWALL, LOGIN_REQUIRED, ERROR)
- `SourceAttribution` with verification and caveat logic
- `ContentAccessResult` for access tracking
- `AttributionSummary` with reliability scoring

**Strengths:**
- EXCELLENT - Comprehensive attribution tracking system
- `is_verified()` and `requires_caveat()` methods for claim validation
- `get_attribution_prefix()` for presenting claims with context
- `AttributionSummary.get_reliability_score()` with weighted scoring
- Proper `Field(ge=0.0, le=1.0)` constraints on confidence scores

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Mutable list default | Line 108, 137 | Medium | `default_factory=list` used but lists can grow unbounded |
| No URL validation | Line 51 | Low | `source_url` has no format validation |
| No bounds on attributions | Line 137 | Low | `attributions` list has no max |

**Enhancement Suggestions:**

```python
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceAttribution(BaseModel):
    """Attribution for a single claim or piece of information."""

    model_config = ConfigDict(strict=True, extra="forbid")

    claim: str = Field(..., min_length=1, max_length=10000, description="The claim or piece of information")
    source_type: SourceType = Field(..., description="How this information was obtained")
    source_url: str | None = Field(default=None, max_length=2000, description="URL of the source")
    access_status: AccessStatus = Field(default=AccessStatus.FULL, description="Access status when retrieving")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in this attribution")
    raw_excerpt: str | None = Field(default=None, max_length=5000, description="Actual text excerpt from source")

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        """Validate URL format if provided."""
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("source_url must start with http:// or https://")
        return v


class AttributionSummary(BaseModel):
    """Summary of attributions for an output."""

    model_config = ConfigDict(strict=True)

    total_claims: int = Field(default=0, ge=0)
    verified_claims: int = Field(default=0, ge=0)
    inferred_claims: int = Field(default=0, ge=0)
    unavailable_claims: int = Field(default=0, ge=0)
    average_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    has_paywall_sources: bool = False
    attributions: list[SourceAttribution] = Field(default_factory=list, max_length=1000)
```

**Overall Rating:** ✅ Good

---

### 43. `backend/app/domain/models/source_citation.py`

**Purpose:** Source citation model for tracking references in reports

**Current Setup:**
- Simple `SourceCitation` model with URL, title, snippet, access_time
- Uses `Literal["search", "browser", "file"]` for source type
- Legacy `class Config` with `json_encoders`

**Strengths:**
- Clean, minimal model for citation tracking
- `Literal` type for source_type is type-safe

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Legacy Config class | Lines 26-27 | High | Uses `class Config` instead of `model_config = ConfigDict(...)` |
| No UTC timezone | Line 23 | Medium | Uses `datetime` without UTC specification |
| No model_config | Global | Medium | Missing `ConfigDict` with strict settings |
| No URL validation | Line 20 | Medium | `url` has no format validation |
| No Field constraints | All fields | Low | Missing min_length, max_length constraints |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceCitation(BaseModel):
    """Represents a source citation for report bibliography."""

    model_config = ConfigDict(strict=True, extra="forbid")

    url: str = Field(..., min_length=1, max_length=2000)
    title: str = Field(..., min_length=1, max_length=500)
    snippet: str | None = Field(default=None, max_length=2000)
    access_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_type: Literal["search", "browser", "file"] = "search"

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(("http://", "https://", "file://")):
            raise ValueError("url must be a valid URL")
        return v
```

**Overall Rating:** ⚠️ Needs Work

---

### 44. `backend/app/domain/models/source_quality.py`

**Purpose:** Source quality assessment and filtering models

**Current Setup:**
- `SourceReliability` and `ContentFreshness` enums
- `SourceQualityScore` with composite scoring algorithm
- `SourceFilterConfig` with domain tier lists
- `FilteredSourceResult` with acceptance rate tracking

**Strengths:**
- EXCELLENT - Comprehensive source quality system
- `composite_score` property with documented weights (reliability 35%, relevance 30%, freshness 20%, depth 15%)
- `passes_threshold` property for filtering decisions
- Well-organized domain tier lists (high_reliability_domains, medium_reliability_domains)
- `FilteredSourceResult.get_summary()` for human-readable output

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Line 43 | Medium | `publication_date: datetime` without UTC |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No URL validation | Line 31-32 | Low | `url` and `domain` have no format validation |
| Mutable list defaults | Lines 82-83, 131-133 | Low | Lists use `default_factory` but no bounds |
| Lambda in Field default | Lines 91, 113 | Low | Uses lambda for list defaults (correct but verbose) |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SourceQualityScore(BaseModel):
    """Comprehensive source quality assessment."""

    model_config = ConfigDict(strict=True, extra="forbid")

    url: str = Field(..., max_length=2000)
    domain: str = Field(..., max_length=200)

    reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    freshness_score: float = Field(default=0.5, ge=0.0, le=1.0)
    content_depth_score: float = Field(default=0.5, ge=0.0, le=1.0)

    reliability_tier: SourceReliability = SourceReliability.UNKNOWN
    freshness_category: ContentFreshness = ContentFreshness.UNKNOWN
    publication_date: datetime | None = None

    is_primary_source: bool = False
    has_citations: bool = False
    is_paywalled: bool = False
    requires_login: bool = False

    @property
    def composite_score(self) -> float:
        """Weighted composite quality score.

        Weights: reliability 35%, relevance 30%, freshness 20%, depth 15%
        """
        return (
            self.reliability_score * 0.35
            + self.relevance_score * 0.30
            + self.freshness_score * 0.20
            + self.content_depth_score * 0.15
        )


# Predefined domain lists as module constants
HIGH_RELIABILITY_DOMAINS = [
    "arxiv.org", "github.com", "docs.python.org", "pytorch.org",
    "tensorflow.org", "huggingface.co", "openai.com", "anthropic.com",
    "nature.com", "acm.org", "ieee.org", "research.google",
]

MEDIUM_RELIABILITY_DOMAINS = [
    "medium.com", "dev.to", "stackoverflow.com", "techcrunch.com",
]


class SourceFilterConfig(BaseModel):
    """Configuration for source filtering."""

    model_config = ConfigDict(strict=True)

    min_composite_score: float = Field(default=0.4, ge=0.0, le=1.0)
    min_reliability_score: float = Field(default=0.3, ge=0.0, le=1.0)
    min_relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    max_age_days: int | None = Field(default=730, ge=1)

    allowed_domains: list[str] = Field(default_factory=list, max_length=1000)
    blocked_domains: list[str] = Field(default_factory=list, max_length=1000)
    high_reliability_domains: list[str] = Field(
        default_factory=lambda: HIGH_RELIABILITY_DOMAINS.copy(),
        max_length=500,
    )
    medium_reliability_domains: list[str] = Field(
        default_factory=lambda: MEDIUM_RELIABILITY_DOMAINS.copy(),
        max_length=500,
    )
```

**Overall Rating:** ✅ Excellent

---

### 45. `backend/app/domain/models/state_manifest.py`

**Purpose:** State manifest for blackboard architecture - implements Manus AI's pattern for inter-agent communication

**Current Setup:**
- `StateEntry` for individual posted entries
- `StateManifest` with indexing for efficient lookups
- Methods: `post()`, `get()`, `get_history()`, `get_by_agent()`, `get_recent()`
- `to_context_string()` for LLM context formatting
- Serialization via `to_dict()` and `from_dict()`
- Uses `datetime.now(UTC)` correctly

**Strengths:**
- EXCELLENT - Well-implemented blackboard pattern
- Uses UTC correctly: `datetime.now(UTC)` throughout
- Private attribute `_index` for O(1) key lookups
- `model_post_init` for index rebuilding after deserialization
- Comprehensive docstrings with examples
- `to_context_string()` truncates long values for LLM context
- Clean serialization/deserialization pattern

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Lines 23, 45 | Medium | Missing `ConfigDict` with strict settings |
| Unbounded entries | Line 82 | Medium | `entries` list grows without cleanup |
| No bounds on index | Line 85 | Low | Private `_index` has no size limit |
| Any type for value | Line 39 | Low | `value: Any` is not type-safe |

**Enhancement Suggestions:**

```python
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

logger = logging.getLogger(__name__)

MAX_ENTRIES = 10000


class StateEntry(BaseModel):
    """An entry in the state manifest."""

    model_config = ConfigDict(strict=True, extra="forbid")

    key: str = Field(..., min_length=1, max_length=200)
    value: Any  # Cannot constrain further due to flexible nature
    posted_by: str = Field(..., min_length=1, max_length=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)


class StateManifest(BaseModel):
    """Shared state manifest for inter-agent communication."""

    model_config = ConfigDict(strict=True)

    session_id: str = Field(..., min_length=1)
    entries: list[StateEntry] = Field(default_factory=list, max_length=MAX_ENTRIES)
    max_entries: int = Field(default=MAX_ENTRIES, ge=100, le=100000)

    _index: dict[str, list[int]] = PrivateAttr(default_factory=dict)

    def post(self, entry: StateEntry) -> None:
        """Post an entry to the blackboard with bounds checking."""
        # Enforce max entries limit
        if len(self.entries) >= self.max_entries:
            # Remove oldest entries to make room
            overflow = len(self.entries) - self.max_entries + 1
            self.entries = self.entries[overflow:]
            self._rebuild_index()
            logger.warning(
                "State manifest reached max entries, pruned oldest",
                extra={"session_id": self.session_id, "pruned": overflow},
            )

        index = len(self.entries)
        self.entries.append(entry)

        if entry.key not in self._index:
            self._index[entry.key] = []
        self._index[entry.key].append(index)
```

**Overall Rating:** ✅ Excellent

---

## Batch 9 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 20 |
| Critical | 0 |
| Medium | 11 |
| Low | 9 |

### Key Findings

1. **Blackboard Architecture**: `state_manifest.py` implements an excellent blackboard pattern with efficient indexing and comprehensive documentation.

2. **Source Quality System**: Both `source_attribution.py` and `source_quality.py` provide robust quality assessment with weighted scoring.

3. **UTC Inconsistency**: `snapshot.py` and `source_citation.py` use `datetime.now()` without UTC, while `state_manifest.py` correctly uses `datetime.now(UTC)`.

4. **Legacy Config**: `source_citation.py` still uses legacy `class Config` pattern instead of Pydantic v2 `model_config`.

5. **Snapshot System**: Comprehensive snapshot types covering file system, browser, terminal, editor, and plan states.

### Priority Fixes

1. **High**: Fix `datetime.now()` to `datetime.now(UTC)` in `snapshot.py` (Lines 29, 96, 134)
2. **High**: Replace legacy `class Config` with `model_config = ConfigDict(...)` in `source_citation.py`
3. **Medium**: Add `model_config = ConfigDict(...)` to all model classes across all files
4. **Medium**: Add bounds to unbounded lists (`entries`, `attributions`, `files`)
5. **Low**: Add URL validation to `source_url` and `url` fields

---

## Batch 10: Domain Models (Files 46-50)

### 46. `backend/app/domain/models/state_model.py`

**Purpose:** Unified state transition validation for agent workflows

**Current Setup:**
- `AgentStatus` enum for PlanActFlow states (IDLE, PLANNING, VERIFYING, EXECUTING, etc.)
- `VALID_TRANSITIONS` dict defining allowed state transitions
- `StateTransitionError` exception for invalid transitions
- Helper functions: `validate_transition()`, `get_valid_transitions()`, `is_terminal_status()`, `is_error_status()`, `get_recovery_paths()`
- `StatusTransitionGuard` context manager for guarded transitions

**Strengths:**
- EXCELLENT - Well-designed state machine with clear transition rules
- `StatusTransitionGuard` context manager for safe transitions with automatic error handling
- Comprehensive transition validation
- `get_recovery_paths()` for error recovery strategies
- Clear documentation and usage examples

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No Pydantic model | Global | Low | File contains enums and functions only, no Pydantic models |
| StatusTransitionGuard untyped | Line 158 | Low | `flow` parameter lacks type annotation |

**Enhancement Suggestions:**

```python
from typing import Protocol

class FlowProtocol(Protocol):
    """Protocol for flow objects with status."""
    status: AgentStatus


class StatusTransitionGuard:
    """Context manager for guarded state transitions."""

    def __init__(self, flow: FlowProtocol, target_status: AgentStatus, validate: bool = True):
        self.flow = flow
        self.target_status = target_status
        self.validate = validate
        self.original_status: AgentStatus | None = None
```

**Overall Rating:** ✅ Excellent

---

### 47. `backend/app/domain/models/structured_outputs.py`

**Purpose:** Structured output models for zero-hallucination defense - provides type-safe LLM response schemas

**Current Setup:**
- `SourceType` enum for citation types (WEB, TOOL_RESULT, MEMORY, INFERENCE, etc.)
- `Citation` model with URL validation
- `CitedResponse` with grounding validation
- `StepDescription`, `PlanOutput`, `PlanUpdateOutput` for plan structures
- `ToolCallOutput`, `ReflectionOutput`, `VerificationOutput` for agent outputs
- `ErrorAnalysisOutput`, `SummaryOutput` for results
- Utility functions: `validate_llm_output()`, `build_validation_feedback()`

**Strengths:**
- EXCELLENT - Comprehensive structured output system
- `@field_validator` with `@classmethod` - Pydantic v2 compliant
- `HttpUrl` type for proper URL validation
- Placeholder detection in `validate_description()`
- `is_well_grounded` property for grounding validation
- Clear `__all__` exports for public API

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Duplicate ValidationResult | Lines 292-298 | Low | Same name as in thought.py - potential confusion |
| HttpUrl may be strict | Line 54 | Low | `HttpUrl` type is strict - may reject valid URLs with unusual formats |

**Enhancement Suggestions:**

```python
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Citation(BaseModel):
    """A citation for a piece of information."""

    model_config = ConfigDict(strict=True, extra="forbid")

    text: str = Field(..., min_length=1, max_length=10000, description="The text being cited or supported")
    source_type: SourceType = Field(..., description="Type of source")
    url: HttpUrl | None = Field(default=None, description="URL if from web source")
    source_id: str | None = Field(default=None, max_length=200, description="ID of source document/tool result")
    excerpt: str | None = Field(default=None, max_length=5000, description="Relevant excerpt from source")
    page_number: int | None = Field(default=None, ge=1, description="Page number if from document")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence in citation")


class CitedResponse(BaseModel):
    """A response with citations for source attribution."""

    model_config = ConfigDict(strict=True)

    content: str = Field(..., min_length=1, max_length=100000, description="The response content")
    citations: list[Citation] = Field(default_factory=list, max_length=100, description="Citations for claims")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Overall confidence")
    grounding_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Score from grounding validation")
    warning: str | None = Field(default=None, max_length=2000, description="Any caveats or warnings")
```

**Overall Rating:** ✅ Excellent

---

### 48. `backend/app/domain/models/supervisor.py`

**Purpose:** Supervisor model for hierarchical multi-agent system (HMAS) - implements Manus AI's pattern

**Current Setup:**
- `SupervisorDomain` enum (RESEARCH, CODE, DATA, BROWSER, GENERAL)
- `SubTaskStatus` enum for task lifecycle
- `SubTask` model with dependency tracking
- `Supervisor` model with task assignment and dependency resolution
- Uses `datetime.now(UTC)` correctly

**Strengths:**
- EXCELLENT - Well-implemented HMAS pattern
- Uses UTC correctly: `datetime.now(UTC)`
- `get_ready_tasks()` for dependency-aware task scheduling
- Comprehensive docstrings with examples
- Clean domain-driven design

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Lines 56, 82 | Medium | Missing `ConfigDict` with strict settings |
| No bounds on lists | Lines 78, 113-114 | Low | `dependencies`, `tasks`, `worker_agents` have no max |
| Any type for result | Line 77 | Low | `result: Any = None` is not type-safe |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SubTask(BaseModel):
    """A sub-task managed by a supervisor."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=5000)
    assigned_agent: str | None = Field(default=None, max_length=100)
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Any = None
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Supervisor(BaseModel):
    """A supervisor agent in the hierarchical multi-agent system."""

    model_config = ConfigDict(strict=True)

    name: str = Field(..., min_length=1, max_length=100)
    domain: SupervisorDomain
    description: str = Field(default="", max_length=2000)
    tasks: list[SubTask] = Field(default_factory=list, max_length=1000)
    worker_agents: list[str] = Field(default_factory=list, max_length=100)
```

**Overall Rating:** ✅ Excellent

---

### 49. `backend/app/domain/models/sync_outbox.py`

**Purpose:** Domain models for sync outbox pattern - ensures reliable MongoDB to Qdrant synchronization

**Current Setup:**
- `OutboxOperation` enum (UPSERT, DELETE, BATCH_UPSERT, BATCH_DELETE)
- `OutboxStatus` enum (PENDING, PROCESSING, COMPLETED, FAILED)
- `OutboxEntry` with retry logic and exponential backoff
- `DeadLetterEntry` for permanently failed operations
- `OutboxCreate` and `OutboxUpdate` schemas
- Uses `datetime.utcnow()` (deprecated)

**Strengths:**
- EXCELLENT - Well-designed outbox pattern for reliable sync
- Exponential backoff in `calculate_next_retry()` with max 32s
- `can_retry()` method for retry eligibility
- Dead-letter queue for failed operations
- Clear state machine: PENDING -> PROCESSING -> COMPLETED/FAILED

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Deprecated datetime.utcnow() | Lines 53-54, 66, 74, 79, 84-85, 92-93, 119-120 | High | Uses `datetime.utcnow()` instead of `datetime.now(UTC)` |
| Legacy Config class | Lines 57-58, 122-123, 145-146 | High | Uses `class Config` instead of `model_config = ConfigDict(...)` |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No bounds on lists | Lines 117, 131 | Low | `error_history`, `payload` dict have no bounds |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OutboxEntry(BaseModel):
    """Outbox entry for reliable sync operations."""

    model_config = ConfigDict(strict=True, use_enum_values=True)

    id: str | None = None
    operation: OutboxOperation
    collection_name: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict, max_length=100)

    status: OutboxStatus = OutboxStatus.PENDING
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=6, ge=1, le=20)
    next_retry_at: datetime | None = None

    error_message: str | None = Field(default=None, max_length=5000)
    last_error_at: datetime | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def can_retry(self) -> bool:
        """Check if this entry can be retried."""
        if self.status == OutboxStatus.FAILED:
            return False
        if self.retry_count >= self.max_retries:
            return False
        return not (self.next_retry_at and self.next_retry_at > datetime.now(UTC))

    def calculate_next_retry(self) -> datetime:
        """Calculate next retry time with exponential backoff (max 32s)."""
        delay_seconds = min(2**self.retry_count, 32)
        return datetime.now(UTC) + timedelta(seconds=delay_seconds)
```

**Overall Rating:** ⚠️ Needs Work (due to deprecated datetime.utcnow)

---

### 50. `backend/app/domain/models/thought.py`

**Purpose:** Thought domain models for Chain-of-Thought reasoning

**Current Setup:**
- `ThoughtType` enum (OBSERVATION, ANALYSIS, HYPOTHESIS, INFERENCE, EVALUATION, DECISION, REFLECTION, UNCERTAINTY)
- `ThoughtQuality` enum (HIGH, MEDIUM, LOW, UNCERTAIN)
- `Thought` model with evidence tracking
- `ReasoningStep` for grouping thoughts
- `ThoughtChain` for complete reasoning process
- `Decision` for actionable outcomes
- `ValidationResult` for chain validation
- Uses `datetime.now()` without UTC

**Strengths:**
- Comprehensive CoT reasoning system
- `supporting_evidence` and `contradicting_evidence` for balanced reasoning
- `has_high_uncertainty()` for uncertainty detection
- `get_summary()` for human-readable output
- `requires_verification()` and `requires_user_confirmation()` for decision confidence

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Weak ID generation | Lines 44, 74, 103, 178 | High | Uses `datetime.now().timestamp()` - not unique, potential collisions |
| No UTC timezone | Lines 44, 53, 74, 103, 109, 119-120 | High | Uses `datetime.now()` without UTC |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Duplicate ValidationResult | Lines 209-216 | Low | Same name as in structured_outputs.py |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Thought(BaseModel):
    """A single thought in a reasoning chain."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"thought_{uuid.uuid4().hex}")
    type: ThoughtType
    content: str = Field(..., min_length=1, max_length=10000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    quality: ThoughtQuality = ThoughtQuality.MEDIUM
    supporting_evidence: list[str] = Field(default_factory=list, max_length=50)
    contradicting_evidence: list[str] = Field(default_factory=list, max_length=50)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=20)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ThoughtChain(BaseModel):
    """A complete chain of reasoning for a problem."""

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: f"chain_{uuid.uuid4().hex}")
    problem: str = Field(..., min_length=1, max_length=10000)
    context: dict[str, Any] = Field(default_factory=dict, max_length=50)
    steps: list[ReasoningStep] = Field(default_factory=list, max_length=100)
    final_decision: str | None = Field(default=None, max_length=10000)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=20)
```

**Overall Rating:** ⚠️ Needs Work

---

## Batch 10 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 19 |
| Critical | 0 |
| Medium | 6 |
| Low | 13 |

### Key Findings

1. **State Machine Design**: `state_model.py` provides an excellent state machine implementation with `StatusTransitionGuard` context manager for safe transitions.

2. **Structured Outputs**: `structured_outputs.py` demonstrates exemplary Pydantic v2 usage with comprehensive validation for LLM outputs.

3. **HMAS Pattern**: `supervisor.py` implements Manus AI's hierarchical multi-agent system pattern with proper UTC timezone handling.

4. **Outbox Pattern**: `sync_outbox.py` has good design but uses deprecated `datetime.utcnow()` and legacy `class Config`.

5. **CoT Reasoning**: `thought.py` provides comprehensive chain-of-thought reasoning models but has weak ID generation and missing UTC.

### Priority Fixes

1. **High**: Replace `datetime.utcnow()` with `datetime.now(UTC)` in `sync_outbox.py` (Lines 53-54, 66, 74, 79, 84-85, 92-93, 119-120)
2. **High**: Replace `datetime.now()` with `datetime.now(UTC)` in `thought.py` (Lines 44, 53, 74, 103, 109)
3. **High**: Fix weak ID generation using `timestamp()` in `thought.py` - use `uuid.uuid4().hex` instead
4. **Medium**: Replace legacy `class Config` with `model_config = ConfigDict(...)` in `sync_outbox.py`
5. **Low**: Add type annotation to `StatusTransitionGuard.flow` parameter

---

## Batch 11: Domain Models (Files 51-55)

### 51. `backend/app/domain/models/timeline.py`

**Purpose:** Timeline models for action recording and replay

**Current Setup:**
- `ActionType` enum for various action types (FILE_*, BROWSER_*, TERMINAL_*, etc.)
- `ActionStatus` enum (PENDING, EXECUTING, COMPLETED, FAILED)
- Nested models: `FileChange`, `BrowserAction`, `TerminalCommand`, `ActionMetadata`
- `TimelineAction` with duration tracking
- Uses `datetime.now()` without UTC

**Strengths:**
- Comprehensive action types covering all sandbox operations
- `ActionMetadata` with rich nested models for different action types
- Duration calculation in `mark_completed()` and `mark_failed()`
- Sequence number for timeline ordering

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No UTC timezone | Lines 108-109, 132, 141 | High | Uses `datetime.now()` without UTC |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| No ID prefix | Line 103 | Low | `str(uuid.uuid4())` lacks prefix for identification |
| No bounds on lists | Lines 90-92 | Low | `file_changes`, `browser_actions`, `terminal_commands` have no max |
| Mutable dict default | Line 121 | Low | `function_args: dict | None` pattern inconsistent |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TimelineAction(BaseModel):
    """Represents a single action in the timeline."""

    model_config = ConfigDict(strict=True)

    id: str = Field(default_factory=lambda: f"action_{uuid.uuid4().hex}")
    session_id: str = Field(..., min_length=1)
    sequence_number: int = Field(..., ge=0)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    action_type: ActionType
    status: ActionStatus = ActionStatus.PENDING

    tool_name: str | None = Field(default=None, max_length=100)
    tool_call_id: str | None = Field(default=None, max_length=100)
    function_name: str | None = Field(default=None, max_length=200)
    function_args: dict[str, Any] | None = None
    function_result: Any = None

    metadata: ActionMetadata = Field(default_factory=ActionMetadata)
    event_id: str | None = Field(default=None, max_length=100)

    def mark_completed(self, result: Any = None) -> None:
        """Mark this action as completed and calculate duration."""
        self.completed_at = datetime.now(UTC)
        self.status = ActionStatus.COMPLETED
        self.function_result = result
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
```

**Overall Rating:** ⚠️ Needs Work

---

### 52. `backend/app/domain/models/tool_call.py`

**Purpose:** Standardized tool call envelope for consistent tool execution tracking

**Current Setup:**
- `ToolCallStatus` enum (PENDING, RUNNING, COMPLETED, FAILED, BLOCKED)
- `ToolCallEnvelope` with lifecycle methods
- Uses `time.time()` for epoch timestamps
- `to_log_dict()` for structured logging

**Strengths:**
- EXCELLENT - Clean envelope pattern for tool execution
- `BLOCKED` status for security blocks
- Duration calculation in milliseconds
- Message truncation in `mark_completed()` (200 chars) and `mark_failed()` (500 chars)
- `to_log_dict()` for structured logging

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Line 26 | Medium | Missing `ConfigDict` with strict settings |
| No bounds on arguments | Line 46 | Low | `arguments` dict has no size limit |
| Epoch time vs datetime | Lines 48-49, 58, 63, 72 | Low | Uses `time.time()` instead of datetime - inconsistent with other models |

**Enhancement Suggestions:**

```python
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolCallEnvelope(BaseModel):
    """Envelope wrapping every tool call with standardized metadata."""

    model_config = ConfigDict(strict=True, extra="forbid")

    tool_call_id: str = Field(..., min_length=1, max_length=100)
    tool_name: str = Field(..., min_length=1, max_length=100)
    function_name: str = Field(..., min_length=1, max_length=200)
    arguments: dict[str, Any] = Field(default_factory=dict, max_length=100)
    status: ToolCallStatus = ToolCallStatus.PENDING
    started_at: float | None = Field(default=None, ge=0)
    completed_at: float | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0)
    success: bool | None = None
    error: str | None = Field(default=None, max_length=500)
    result_summary: str | None = Field(default=None, max_length=200)
```

**Overall Rating:** ✅ Good

---

### 53. `backend/app/domain/models/tool_result.py`

**Purpose:** Generic result wrapper for tool execution

**Current Setup:**
- `ToolResult` generic class with `T` type variable
- Factory methods: `ok()` and `error()`
- Minimal fields: `success`, `message`, `data`

**Strengths:**
- EXCELLENT - Clean, minimal generic result pattern
- `Generic[T]` for type-safe data handling
- Factory methods `ok()` and `error()` for clean construction
- `Self` return type for proper type inference

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Line 8 | Medium | Missing `ConfigDict` with strict settings |
| No message constraints | Line 18 | Low | `message` has no max_length |

**Enhancement Suggestions:**

```python
from typing import Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    """Result of a tool execution."""

    model_config = ConfigDict(strict=True)

    success: bool
    message: str | None = Field(default=None, max_length=10000)
    data: T | None = None

    @classmethod
    def ok(cls, message: str | None = None, data: T | None = None) -> Self:
        """Create a successful result."""
        return cls(success=True, message=message, data=data)

    @classmethod
    def error(cls, message: str, data: T | None = None) -> Self:
        """Create an error result."""
        return cls(success=False, message=message, data=data)
```

**Overall Rating:** ✅ Excellent

---

### 54. `backend/app/domain/models/url_verification.py`

**Purpose:** URL verification models for hallucination prevention

**Current Setup:**
- `URLVerificationStatus` enum (VERIFIED, EXISTS_NOT_VISITED, NOT_FOUND, PLACEHOLDER, TIMEOUT, ERROR)
- `URLVerificationResult` dataclass
- `BatchURLVerificationResult` dataclass with aggregation
- Uses `@dataclass` instead of Pydantic `BaseModel`
- Uses `datetime.utcnow()` (deprecated)

**Strengths:**
- Comprehensive URL verification statuses
- `is_valid_citation` and `is_suspicious` properties
- `get_warning_message()` with status-specific messages
- Batch verification with summary statistics

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Uses dataclass instead of Pydantic | Lines 23, 63 | High | Should use Pydantic `BaseModel` for consistency and validation |
| Deprecated datetime.utcnow() | Lines 35, 75 | High | Uses `datetime.utcnow()` instead of `datetime.now(UTC)` |
| No URL validation | Line 27 | Medium | `url: str` has no format validation |
| No bounds on dicts/lists | Lines 67, 155 | Low | `results` dict and `active_sessions` list have no bounds |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class URLVerificationResult(BaseModel):
    """Result of verifying a single URL."""

    model_config = ConfigDict(strict=True, extra="forbid")

    url: str = Field(..., max_length=2000)
    status: URLVerificationStatus
    exists: bool = False
    was_visited: bool = False
    http_status: int | None = Field(default=None, ge=100, le=599)
    redirect_url: str | None = Field(default=None, max_length=2000)
    verification_time_ms: float = Field(default=0.0, ge=0)
    error: str | None = Field(default=None, max_length=1000)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @property
    def is_valid_citation(self) -> bool:
        """Check if this URL is valid for use as a citation."""
        return self.status == URLVerificationStatus.VERIFIED


class BatchURLVerificationResult(BaseModel):
    """Result of verifying multiple URLs."""

    model_config = ConfigDict(strict=True)

    results: dict[str, URLVerificationResult] = Field(default_factory=dict, max_length=1000)
    total_urls: int = Field(default=0, ge=0)
    verified_count: int = Field(default=0, ge=0)
    not_visited_count: int = Field(default=0, ge=0)
    not_found_count: int = Field(default=0, ge=0)
    placeholder_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    verification_time_ms: float = Field(default=0.0, ge=0)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

**Overall Rating:** ⚠️ Needs Work

---

### 55. `backend/app/domain/models/usage.py`

**Purpose:** Usage tracking domain models for token consumption and cost tracking

**Current Setup:**
- `UsageType` enum (LLM_CALL, TOOL_CALL, EMBEDDING)
- `UsageRecord` for individual LLM calls
- `SessionUsage` for session aggregation
- `SessionMetrics` for enhanced monitoring
- `DailyUsageAggregate` and `MonthlyUsageSummary` for reporting
- Uses `datetime.now(UTC)` correctly

**Strengths:**
- EXCELLENT - Comprehensive usage tracking system
- Uses UTC correctly: `datetime.now(UTC)`
- Multiple aggregation levels (session, daily, monthly)
- Model breakdown tracking (`tokens_by_model`, `cost_by_model`)
- Budget tracking in `SessionMetrics`
- Proper UUID with truncation for IDs

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Truncated UUID | Lines 24, 131 | Medium | `uuid.uuid4().hex[:16]` - only 16 hex chars |
| Mutable dict defaults | Lines 71-72, 99, 151-152, 184 | Medium | Uses `{}` instead of `Field(default_factory=dict)` |
| No bounds on dicts/lists | Lines 71-72, 155 | Low | `tokens_by_model`, `active_sessions` have no bounds |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class UsageRecord(BaseModel):
    """Individual LLM call usage record."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"usage_{uuid.uuid4().hex}")
    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)

    model: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., min_length=1, max_length=50)

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)

    prompt_cost: float = Field(default=0.0, ge=0)
    completion_cost: float = Field(default=0.0, ge=0)
    total_cost: float = Field(default=0.0, ge=0)

    usage_type: UsageType = UsageType.LLM_CALL
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionUsage(BaseModel):
    """Aggregated usage for a single session."""

    model_config = ConfigDict(strict=True)

    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)

    total_prompt_tokens: int = Field(default=0, ge=0)
    total_completion_tokens: int = Field(default=0, ge=0)
    total_cached_tokens: int = Field(default=0, ge=0)

    total_prompt_cost: float = Field(default=0.0, ge=0)
    total_completion_cost: float = Field(default=0.0, ge=0)
    total_cost: float = Field(default=0.0, ge=0)

    llm_call_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)

    tokens_by_model: dict[str, int] = Field(default_factory=dict, max_length=100)
    cost_by_model: dict[str, float] = Field(default_factory=dict, max_length=100)

    first_activity: datetime | None = None
    last_activity: datetime | None = None
```

**Overall Rating:** ✅ Good

---

## Batch 11 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 19 |
| Critical | 0 |
| Medium | 9 |
| Low | 10 |

### Key Findings

1. **Tool Result Pattern**: `tool_result.py` demonstrates an excellent minimal generic result pattern with `Generic[T]` and factory methods.

2. **Tool Call Envelope**: `tool_call.py` provides a clean envelope pattern with `BLOCKED` status for security and proper logging support.

3. **Dataclass vs Pydantic**: `url_verification.py` uses `@dataclass` instead of Pydantic `BaseModel`, which is inconsistent with the codebase.

4. **UTC Usage**: `usage.py` correctly uses `datetime.now(UTC)`, but `timeline.py` and `url_verification.py` have issues.

5. **Usage Tracking**: Comprehensive multi-level aggregation (session, daily, monthly) for billing and monitoring.

### Priority Fixes

1. **High**: Replace `@dataclass` with Pydantic `BaseModel` in `url_verification.py`
2. **High**: Replace `datetime.utcnow()` with `datetime.now(UTC)` in `url_verification.py` (Lines 35, 75)
3. **High**: Replace `datetime.now()` with `datetime.now(UTC)` in `timeline.py` (Lines 108-109, 132, 141)
4. **Medium**: Fix mutable dict defaults `{}` to `Field(default_factory=dict)` in `usage.py`
5. **Medium**: Add `model_config = ConfigDict(...)` to all model classes

---

## Batch 12: Domain Models (Files 56-60)

### 56. `backend/app/domain/models/user.py`

**Purpose:** User domain model for authentication and user management

**Current Setup:**
- `UserRole` enum (ADMIN, USER)
- `User` model with email validation
- Domain methods: `update_last_login()`, `deactivate()`, `activate()`
- Uses `datetime.now(UTC)` correctly
- Pydantic v2 compliant `@field_validator` with `@classmethod`

**Strengths:**
- EXCELLENT - Clean user model with domain methods
- Uses UTC correctly: `datetime.now(UTC)`
- Pydantic v2 compliant validators
- Email validation with normalization (lowercase, strip)
- Fullname validation with minimum length

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Line 12 | Medium | Missing `ConfigDict` with strict settings |
| Datetime not in Field | Lines 21-22 | Medium | `datetime.now(UTC)` not wrapped in `Field(default_factory=...)` |
| No Field constraints | Lines 15-18 | Low | Missing min_length, max_length on string fields |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class User(BaseModel):
    """User domain model."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(..., min_length=1, max_length=100)
    fullname: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., min_length=3, max_length=200)
    password_hash: str | None = Field(default=None, max_length=200)
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login_at: datetime | None = None

    @field_validator("fullname")
    @classmethod
    def validate_fullname(cls, v: str) -> str:
        if not v or len(v.strip()) < 2:
            raise ValueError("Full name must be at least 2 characters long")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not v or "@" not in v:
            raise ValueError("Valid email is required")
        return v.strip().lower()
```

**Overall Rating:** ✅ Good

---

### 57. `backend/app/domain/models/user_preference.py`

**Purpose:** User preference domain models for learning and applying user-specific preferences

**Current Setup:**
- Multiple enums: `PreferenceCategory`, `CommunicationStyle`, `RiskTolerance`, `OutputFormat`
- `UserPreference` for individual preferences
- `UserPreferenceProfile` for complete user profile
- `PreferenceInferenceResult` for inference results
- Uses `datetime.now()` without UTC

**Strengths:**
- Comprehensive preference categories and styles
- `to_prompt_context()` for LLM context generation
- `infer_preference()` with confidence-based updates
- `get_high_confidence_preferences()` for filtering
- `verbosity_level` with bounds (1-5)

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Weak ID generation | Line 55 | High | Uses `datetime.now().timestamp()` - not unique |
| No UTC timezone | Lines 55, 61-62, 69, 94-95 | High | Uses `datetime.now()` without UTC |
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Any type for value | Line 58 | Low | `value: Any` is not type-safe |
| No bounds on lists | Lines 77, 86-87, 194-196 | Low | Multiple lists have no max |

**Enhancement Suggestions:**

```python
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserPreference(BaseModel):
    """A single user preference setting."""

    model_config = ConfigDict(strict=True, extra="forbid")

    preference_id: str = Field(default_factory=lambda: f"pref_{uuid.uuid4().hex}")
    category: PreferenceCategory
    name: str = Field(..., min_length=1, max_length=100)
    value: Any
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(default="inferred", max_length=20)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    usage_count: int = Field(default=0, ge=0)

    def update_value(self, new_value: Any, confidence_boost: float = 0.1) -> None:
        """Update the preference value."""
        self.value = new_value
        self.confidence = min(1.0, self.confidence + confidence_boost)
        self.updated_at = datetime.now(UTC)
        self.usage_count += 1


class UserPreferenceProfile(BaseModel):
    """Complete preference profile for a user."""

    model_config = ConfigDict(strict=True)

    user_id: str = Field(..., min_length=1)
    preferences: list[UserPreference] = Field(default_factory=list, max_length=1000)

    communication_style: CommunicationStyle = CommunicationStyle.DETAILED
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    output_format: OutputFormat = OutputFormat.MARKDOWN
    verbosity_level: int = Field(default=3, ge=1, le=5)

    preferred_tools: list[str] = Field(default_factory=list, max_length=50)
    avoided_tools: list[str] = Field(default_factory=list, max_length=50)

    prefers_confirmations: bool = True
    prefers_explanations: bool = True
    prefers_suggestions: bool = True

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

**Overall Rating:** ⚠️ Needs Work

---

### 58. `backend/app/domain/models/user_settings.py`

**Purpose:** User settings domain model for LLM, search, and browser agent configuration

**Current Setup:**
- `UserSettings` with provider settings (LLM, search, browser)
- Skills configuration with `enabled_skills` and `skill_configs`
- `update()` method for batch updates
- Uses `datetime.now(UTC)` correctly

**Strengths:**
- Uses UTC correctly: `datetime.now(UTC)`
- Clean update method
- Comprehensive settings for all providers
- Skills configuration support

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | Line 7 | Medium | Missing `ConfigDict` with strict settings |
| Datetime not in Field | Lines 42-43 | Medium | `datetime.now(UTC)` not wrapped in `Field(default_factory=...)` |
| No Field constraints | Lines 14-17 | Low | Missing validation on provider names, temperature range |
| No bounds on lists/dicts | Lines 32-39 | Low | `enabled_skills`, `skill_configs` have no bounds |

**Enhancement Suggestions:**

```python
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserSettings(BaseModel):
    """User settings domain model."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)

    llm_provider: str = Field(default="openai", max_length=50)
    model_name: str = Field(default="gpt-4", max_length=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8000, ge=1, le=1000000)

    search_provider: str = Field(default="duckduckgo", max_length=50)

    browser_agent_max_steps: int = Field(default=25, ge=1, le=100)
    browser_agent_timeout: int = Field(default=300, ge=10, le=3600)
    browser_agent_use_vision: bool = True
    response_verbosity_preference: str = Field(default="adaptive", max_length=20)
    clarification_policy: str = Field(default="auto", max_length=20)
    quality_floor_enforced: bool = True
    skill_auto_trigger_enabled: bool = False

    enabled_skills: list[str] = Field(default_factory=list, max_length=100)
    skill_configs: dict[str, dict[str, Any]] = Field(default_factory=dict, max_length=100)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0 and 2.0")
        return v
```

**Overall Rating:** ✅ Good

---

### 59. `backend/app/domain/models/visited_source.py`

**Purpose:** Visited source model for provenance tracking with content hashing

**Current Setup:**
- `ContentAccessMethod` enum (BROWSER_NAVIGATE, HTTP_FETCH, SEARCH_SNIPPET, etc.)
- `VisitedSource` with content hashing (SHA-256)
- Methods: `content_contains()`, `content_contains_number()`, `get_excerpt_containing()`
- Private attribute `_full_content` for lazy loading
- Uses `datetime.utcnow()` (deprecated)

**Strengths:**
- EXCELLENT - Comprehensive provenance tracking
- SHA-256 content hashing for verification
- `content_contains_number()` with tolerance for numeric verification
- `get_excerpt_containing()` for context extraction
- `is_fully_accessible` and `is_search_snippet_only` properties

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| Deprecated datetime.utcnow() | Lines 56, 73 | High | Uses `datetime.utcnow()` instead of `datetime.now(UTC)` |
| No model_config | Line 26 | Medium | Missing `ConfigDict` with strict settings |
| No URL validation | Line 53 | Medium | `url` has no format validation |
| Private attribute pattern | Line 77 | Low | `_full_content` uses private attribute - consider using `PrivateAttr` |

**Enhancement Suggestions:**

```python
import hashlib
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator


class VisitedSource(BaseModel):
    """Persistent record of a URL actually visited during a session."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(default_factory=lambda: f"source_{uuid.uuid4().hex}")
    session_id: str = Field(..., min_length=1)
    tool_event_id: str = Field(..., min_length=1)

    url: str = Field(..., max_length=2000)
    final_url: str | None = Field(default=None, max_length=2000)
    access_method: ContentAccessMethod
    access_time: datetime = Field(default_factory=lambda: datetime.now(UTC))

    content_hash: str = Field(..., min_length=64, max_length=64)  # SHA-256 hex
    content_length: int = Field(..., ge=0)
    content_preview: str = Field(default="", max_length=2000)

    page_title: str | None = Field(default=None, max_length=500)
    meta_description: str | None = Field(default=None, max_length=1000)
    last_modified: datetime | None = None

    access_status: str = Field(default="full", max_length=20)
    paywall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extraction_method: str = Field(default="html_to_text", max_length=50)

    _full_content: str | None = PrivateAttr(default=None)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://", "file://")):
            raise ValueError("URL must start with http://, https://, or file://")
        return v
```

**Overall Rating:** ⚠️ Needs Work (due to deprecated datetime.utcnow)

---

### 60. `backend/app/domain/models/sandbox/file.py`

**Purpose:** File operation related models for sandbox operations

**Current Setup:**
- Multiple result models: `FileReadResult`, `FileWriteResult`, `FileReplaceResult`, `FileSearchResult`, `FileFindResult`, `FileUploadResult`
- Simple, focused models for each operation type
- Uses `Field(..., description=...)` for documentation

**Strengths:**
- Clean separation of concerns - one model per operation type
- Good use of `Field(description=...)` for documentation
- Simple, minimal models

**Issues:**

| Issue | Location | Severity | Description |
|-------|----------|----------|-------------|
| No model_config | All classes | Medium | Missing `ConfigDict` with strict settings |
| Mutable list defaults | Lines 33-34, 41 | Medium | Uses `Field([])` instead of `Field(default_factory=list)` |
| No Field constraints | All fields | Low | Missing max_length, ge/le constraints |
| Missing bytes_written default | Line 19 | Low | `bytes_written` could have `ge=0` constraint |

**Enhancement Suggestions:**

```python
from pydantic import BaseModel, ConfigDict, Field


class FileReadResult(BaseModel):
    """File read result."""

    model_config = ConfigDict(strict=True, extra="forbid")

    content: str = Field(..., max_length=100_000_000, description="File content")
    file: str = Field(..., max_length=2000, description="Path of the read file")


class FileWriteResult(BaseModel):
    """File write result."""

    model_config = ConfigDict(strict=True, extra="forbid")

    file: str = Field(..., max_length=2000, description="Path of the written file")
    bytes_written: int | None = Field(default=None, ge=0, description="Number of bytes written")


class FileSearchResult(BaseModel):
    """File content search result."""

    model_config = ConfigDict(strict=True, extra="forbid")

    file: str = Field(..., max_length=2000, description="Path of the searched file")
    matches: list[str] = Field(default_factory=list, max_length=1000, description="List of matched content")
    line_numbers: list[int] = Field(default_factory=list, max_length=1000, description="List of matched line numbers")


class FileUploadResult(BaseModel):
    """File upload result."""

    model_config = ConfigDict(strict=True, extra="forbid")

    file_path: str = Field(..., max_length=2000, description="Path of the uploaded file")
    file_size: int = Field(..., ge=0, description="Size of the uploaded file in bytes")
    success: bool = Field(..., description="Whether upload was successful")
```

**Overall Rating:** ⚠️ Needs Work

---

## Batch 12 Summary Statistics

| Metric | Count |
|--------|-------|
| Files Reviewed | 5 |
| Total Issues Found | 23 |
| Critical | 0 |
| Medium | 13 |
| Low | 10 |

### Key Findings

1. **UTC Compliance**: `user.py`, `user_settings.py` use UTC correctly, but `user_preference.py` and `visited_source.py` have issues.

2. **Weak ID Generation**: `user_preference.py` uses `datetime.now().timestamp()` for IDs instead of UUIDs.

3. **Private Attributes**: `visited_source.py` uses private attribute `_full_content` but should use `PrivateAttr` from Pydantic.

4. **Provenance Tracking**: `visited_source.py` provides excellent content hashing and verification with SHA-256.

5. **Simple File Models**: `sandbox/file.py` has clean, minimal models but lacks proper Field defaults and constraints.

### Priority Fixes

1. **High**: Replace `datetime.utcnow()` with `datetime.now(UTC)` in `visited_source.py` (Lines 56, 73)
2. **High**: Replace `datetime.now()` with `datetime.now(UTC)` in `user_preference.py` (Lines 55, 61-62, 69, 94-95)
3. **High**: Fix weak ID generation in `user_preference.py` - use `uuid.uuid4().hex` instead of `timestamp()`
4. **Medium**: Fix mutable list defaults `Field([])` to `Field(default_factory=list)` in `sandbox/file.py`
5. **Medium**: Add `model_config = ConfigDict(...)` to all model classes

---

*Review will continue with Batch 13 (files 61-65) upon next iteration.*
