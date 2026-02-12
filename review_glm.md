# Pythinker Domain Models Review (GLM)

> Generated: 2026-02-11
> Total Files: ~299
> Progress: 25/299 files reviewed (8.4%)

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
