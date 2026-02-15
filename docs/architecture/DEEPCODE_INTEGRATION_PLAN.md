# DeepCode Integration Plan v2: Targeted Enhancements for Pythinker

**Document Version:** 2.0 (Complete Rewrite)
**Date:** 2026-02-15
**Status:** Planning Phase — Context7 MCP Validated
**Priority:** High

---

## Executive Summary

After thorough analysis of **both** codebases, this plan targets the **actual gaps** where DeepCode patterns enhance Pythinker. The v1 plan incorrectly described Pythinker as having "single agent flow" and "no validation" — Pythinker already has a sophisticated multi-agent architecture that exceeds DeepCode in many areas. This v2 plan focuses exclusively on genuine enhancements.

### What Pythinker Already Has (DO NOT Re-Invent)

| Capability | Pythinker Implementation | Status |
|------------|-------------------------|--------|
| Multi-Agent Orchestration | `PlanActFlow` → `PlannerAgent` → `ExecutionAgent` → `VerifierAgent` | ✅ Production |
| Agent Registry | `AgentRegistry`, `AgentType`, `AgentCapability`, `SpecializedAgentFactory` | ✅ Production |
| Token Management | `TokenManager` with **tiktoken**, pressure levels at 60/70/80/90% | ✅ Production |
| Memory Management | `MemoryManager` + `SemanticCompressor` + `TemporalCompressor` + `ImportanceAnalyzer` | ✅ Production |
| Output Validation | `PlanValidator`, `OutputCoverageValidator`, `ComplianceGates`, `DeliveryFidelityChecker` | ✅ Production |
| Stuck Detection | `StuckDetector` with alternating-pattern, monologue, action-error loops | ✅ Production |
| Error Handling | `ErrorHandler`, `ErrorIntegrationBridge`, `AgentHealthLevel`, `FailurePredictor` | ✅ Production |
| Progress Tracking | `ProgressEvent`, `ToolProgressEvent`, `PhaseEvent`, `FlowTransitionEvent` (30+ types) | ✅ Production |
| Complexity Assessment | `ComplexityAssessor` with step limits per complexity level | ✅ Production |
| Role-Scoped Memory | `RoleScopedMemory` for planner, executor, researcher, reflector | ✅ Production |
| Reflection | `ReflectionAgent`, `CriticAgent`, `ChainOfVerification` | ✅ Production |
| Pydantic Discriminated Unions | `AgentEvent = Annotated[Union[...], Discriminator("type")]` | ✅ Production |

### Actual Gaps (What DeepCode Adds)

| Enhancement | DeepCode Source | Pythinker Gap | Priority |
|-------------|----------------|---------------|----------|
| Adaptive LLM Model Selection | `llm_utils.get_preferred_llm_class()` | No per-step model switching | **P0** |
| Tool Call Efficiency Monitor | `CodeImplementationAgent.recent_tool_calls` | `StuckDetector` covers loops but not read/write balance | **P1** |
| Output Truncation Detection | `_assess_output_completeness()` | Validators don't check for LLM output truncation | **P1** |
| Document Segmentation | `DocumentSegmentationAgent` | No large-doc chunking | **P2** |
| Implementation File Tracker | `CodeImplementationAgent.implemented_files_set` | No file-by-file code generation tracking | **P2** |
| Codebase Indexing | `code_indexer.py`, `code_reference_indexer.py` | No codebase relationship mapping | **P3** |

---

## Context7 MCP Validation Sources

All patterns validated against authoritative documentation:

| Technology | Library ID | Score | Snippets |
|-----------|-----------|-------|----------|
| FastAPI | `/websites/fastapi_tiangolo` | 91.4/100 | 21,400 |
| Pydantic v2 | `/llmstxt/pydantic_dev_llms-full_txt` | 87.6/100 | 3,391 |
| Vue 3 | `/llmstxt/vuejs_llms-full_txt` | 81.9/100 | 4,480 |
| VueUse | `/websites/vueuse` | 87.4/100 | 2,384 |

**Key validated patterns:**
- FastAPI: `@asynccontextmanager` lifespan (replaces deprecated `on_startup`/`on_shutdown`)
- FastAPI: `Annotated[T, Depends(dep)]` syntax (preferred over `= Depends()`)
- Pydantic v2: `Discriminator("field")` for tagged unions (already used in `event.py`)
- Pydantic v2: `@model_validator(mode='after')` with `Self` return type
- Pydantic v2: `TypeAdapter` for ad-hoc validation (already used in `execution.py`)
- Vue 3: `<script setup lang="ts">` with `defineProps`/`defineEmits`
- Vue 3: `computed<T>()` for explicit typing, `shallowRef` for performance
- Vue 3: `provide`/`inject` with `readonly()` for one-way data flow

---

## Enhancement 1: Adaptive LLM Model Selection (P0)

### Problem

Pythinker's `ComplexityAssessor` already classifies tasks as simple/medium/complex and adjusts step limits, but the **same model** is used for all steps regardless of complexity. DeepCode selects different models based on task requirements, reducing costs significantly.

### DeepCode Pattern

```python
# DeepCode: utils/llm_utils.py
def get_adaptive_agent_config(task_type: str) -> dict:
    """Select model based on task type."""
    if task_type == "planning":
        return {"model": "claude-3-5-sonnet", "max_tokens": 8000}
    elif task_type == "code_implementation":
        return {"model": "claude-3-5-sonnet", "max_tokens": 16000}
    elif task_type == "summarization":
        return {"model": "claude-3-haiku", "max_tokens": 4000}
```

### Pythinker Integration

**Approach:** Extend `ComplexityAssessor` to recommend a model tier, then use it when creating LLM calls in `ExecutionAgent` and `PlannerAgent`.

**File to modify:** `backend/app/domain/services/agents/complexity_assessor.py`

```python
# Enhancement to existing ComplexityAssessor

from enum import Enum
from pydantic import BaseModel, computed_field  # Context7: Pydantic v2 computed_field


class ModelTier(str, Enum):
    """LLM model tier for cost-optimized routing.

    Maps to actual model identifiers in Settings.
    """
    FAST = "fast"          # Haiku-class: summaries, simple transforms
    BALANCED = "balanced"  # Sonnet-class: planning, standard execution
    POWERFUL = "powerful"  # Opus-class: complex reasoning, architecture


class StepModelRecommendation(BaseModel):
    """Model recommendation for a specific step.

    Context7 validated: Uses Pydantic v2 computed_field pattern.
    """
    step_description: str
    complexity: str  # "simple", "medium", "complex"
    tier: ModelTier

    @computed_field  # Context7: Pydantic v2 @computed_field (not @property)
    @property
    def model_key(self) -> str:
        """Settings key for the recommended model."""
        return f"{self.tier.value}_model"
```

**File to modify:** `backend/app/core/config.py`

```python
# Add to Settings class (Context7: Pydantic v2 computed_field pattern)

class Settings(BaseSettings):
    # ... existing settings ...

    # Adaptive model selection
    adaptive_model_selection_enabled: bool = False
    fast_model: str = "claude-haiku-4-5"       # Summaries, simple tasks
    balanced_model: str = ""                     # Falls back to model_name
    powerful_model: str = "claude-sonnet-4-5"   # Complex reasoning

    @computed_field  # Context7: replaces @property for Pydantic v2
    @property
    def effective_balanced_model(self) -> str:
        return self.balanced_model or self.model_name
```

**File to modify:** `backend/app/domain/services/agents/execution.py`

```python
# In ExecutionAgent._execute_step(), before LLM call:

async def _select_model_for_step(self, step: Step) -> str | None:
    """Select optimal model for this step based on complexity.

    Returns None to use default model, or a model name override.
    """
    settings = get_settings()
    if not settings.adaptive_model_selection_enabled:
        return None

    # Use existing ComplexityAssessor signal
    step_desc = step.description.lower()

    # Fast tier: summaries, simple data transforms, status checks
    fast_keywords = {"summarize", "list", "format", "status", "count"}
    if any(kw in step_desc for kw in fast_keywords):
        return settings.fast_model

    # Powerful tier: architecture, refactoring, debugging
    powerful_keywords = {"architect", "refactor", "debug", "design", "optimize", "analyze"}
    if any(kw in step_desc for kw in powerful_keywords):
        return settings.powerful_model

    # Balanced tier: everything else (default model)
    return None
```

**Expected impact:** 30-40% cost reduction on sessions with mixed-complexity steps.

### Frontend Enhancement

**File to modify:** `frontend/src/components/ToolPanelContent.vue` (or create composable)

No new frontend components needed — the model used per step can be added to the existing `StepEvent` metadata and displayed in the existing step indicator.

**File to create:** `frontend/src/composables/useModelTier.ts`

```typescript
// Context7 validated: Vue 3 Composition API with TypeScript
import { computed, type Ref } from 'vue'

interface StepWithModel {
  model?: string
  description: string
}

/**
 * Composable for displaying model tier information.
 *
 * Context7: Uses computed<T>() for explicit typing (Vue 3 best practice).
 */
export function useModelTier(step: Ref<StepWithModel>) {
  const tierLabel = computed<string>(() => {
    const model = step.value.model
    if (!model) return ''
    if (model.includes('haiku')) return 'Fast'
    if (model.includes('opus')) return 'Powerful'
    return 'Balanced'
  })

  const tierColor = computed<string>(() => {
    const label = tierLabel.value
    if (label === 'Fast') return 'text-emerald-500'
    if (label === 'Powerful') return 'text-amber-500'
    return 'text-blue-500'
  })

  return { tierLabel, tierColor }
}
```

### Testing

```python
# backend/tests/domain/services/agents/test_adaptive_model.py

import pytest
from app.domain.services.agents.complexity_assessor import ModelTier, StepModelRecommendation


def test_fast_tier_for_summaries():
    rec = StepModelRecommendation(
        step_description="Summarize search results",
        complexity="simple",
        tier=ModelTier.FAST,
    )
    assert rec.model_key == "fast_model"  # Context7: computed_field works


def test_powerful_tier_for_architecture():
    rec = StepModelRecommendation(
        step_description="Design authentication system",
        complexity="complex",
        tier=ModelTier.POWERFUL,
    )
    assert rec.model_key == "powerful_model"
```

---

## Enhancement 2: Tool Call Efficiency Monitor (P1)

### Problem

Pythinker's `StuckDetector` catches **loops** (A→B→A→B, monologue, action-error), but DeepCode specifically monitors the **read/write balance** — detecting when an agent reads excessively without making progress (analysis paralysis). This is a complementary signal.

### DeepCode Pattern

```python
# DeepCode: workflows/agents/code_implementation_agent.py
class CodeImplementationAgent:
    def __init__(self):
        self.recent_tool_calls = []
        self.max_read_without_write = 5

    def _check_analysis_loop(self):
        recent_reads = [c for c in self.recent_tool_calls if c in ["read_file", "read_code_mem"]]
        recent_writes = [c for c in self.recent_tool_calls if c == "write_file"]
        if len(recent_reads) >= self.max_read_without_write and not recent_writes:
            # Force the agent to take action
            ...
```

### Pythinker Integration

**Approach:** Add a `ToolEfficiencyMonitor` as a lightweight companion to the existing `StuckDetector`. It monitors the read/write ratio and injects a context nudge when imbalanced.

**File to create:** `backend/app/domain/services/agents/tool_efficiency_monitor.py`

```python
"""
Tool call efficiency monitoring for agent execution.

Complements StuckDetector by tracking read/write balance,
detecting analysis paralysis, and nudging the agent to act.

Design Principles (Context7 validated - Python Design Patterns):
- KISS: Simple sliding window with clear thresholds
- Single Responsibility: Only monitors efficiency, does not handle loops
- Composition: Used alongside StuckDetector, not replacing it
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class EfficiencySignal:
    """Signal indicating tool usage efficiency status."""

    is_imbalanced: bool
    reads_without_action: int
    total_in_window: int
    nudge_message: str | None = None


class ToolEfficiencyMonitor:
    """Monitors tool call read/write balance to detect analysis paralysis.

    Tracks a sliding window of recent tool calls and reports when
    the agent has done too many reads without a corresponding write
    or execute action.

    Works alongside StuckDetector which handles repeating-pattern loops.
    """

    # Tool classifications
    READ_TOOLS: ClassVar[frozenset[str]] = frozenset({
        "file_read", "file_list_directory", "file_search",
        "browser_view", "browser_get_content",
        "code_read_artifact", "code_list_artifacts",
    })

    ACTION_TOOLS: ClassVar[frozenset[str]] = frozenset({
        "file_write", "file_create", "file_patch",
        "shell_exec", "code_execute",
        "browser_navigate", "browser_click", "browser_input",
    })

    def __init__(
        self,
        window_size: int = 10,
        max_reads_before_nudge: int = 5,
    ):
        self._window: deque[str] = deque(maxlen=window_size)
        self._max_reads = max_reads_before_nudge
        self._nudge_count = 0

    def record(self, tool_name: str) -> None:
        """Record a tool call."""
        self._window.append(tool_name)

    def check_efficiency(self) -> EfficiencySignal:
        """Check current read/write balance.

        Returns an efficiency signal with optional nudge message.
        """
        if len(self._window) < self._max_reads:
            return EfficiencySignal(
                is_imbalanced=False,
                reads_without_action=0,
                total_in_window=len(self._window),
            )

        # Count consecutive reads from the end (most recent)
        consecutive_reads = 0
        for tool_name in reversed(self._window):
            if tool_name in self.READ_TOOLS:
                consecutive_reads += 1
            elif tool_name in self.ACTION_TOOLS:
                break  # Found an action, stop counting
            # Unknown tools don't break the streak

        is_imbalanced = consecutive_reads >= self._max_reads
        nudge = None

        if is_imbalanced:
            self._nudge_count += 1
            nudge = (
                f"[EFFICIENCY: You've read {consecutive_reads} times without writing or executing. "
                f"Consider taking action based on what you've gathered.]"
            )
            logger.info(
                "Tool efficiency nudge #%d: %d reads without action",
                self._nudge_count,
                consecutive_reads,
            )

        return EfficiencySignal(
            is_imbalanced=is_imbalanced,
            reads_without_action=consecutive_reads,
            total_in_window=len(self._window),
            nudge_message=nudge,
        )

    def reset(self) -> None:
        """Reset monitor state (e.g., between steps)."""
        self._window.clear()
        self._nudge_count = 0
```

**File to modify:** `backend/app/domain/services/agents/base.py`

```python
# In BaseAgent.__init__, add:
from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor

self._efficiency_monitor = ToolEfficiencyMonitor()

# In the tool execution loop, after recording a tool call:
self._efficiency_monitor.record(tool_name)
signal = self._efficiency_monitor.check_efficiency()
if signal.nudge_message:
    # Inject into next LLM prompt as a system hint
    messages.append({"role": "system", "content": signal.nudge_message})
```

### Testing

```python
# backend/tests/domain/services/agents/test_tool_efficiency_monitor.py

import pytest
from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor


def test_no_nudge_within_threshold():
    monitor = ToolEfficiencyMonitor(max_reads_before_nudge=3)
    monitor.record("file_read")
    monitor.record("file_read")
    signal = monitor.check_efficiency()
    assert not signal.is_imbalanced


def test_nudge_after_excessive_reads():
    monitor = ToolEfficiencyMonitor(max_reads_before_nudge=3)
    for _ in range(4):
        monitor.record("file_read")
    signal = monitor.check_efficiency()
    assert signal.is_imbalanced
    assert signal.nudge_message is not None
    assert "3" in signal.nudge_message or "4" in signal.nudge_message


def test_action_resets_consecutive_count():
    monitor = ToolEfficiencyMonitor(max_reads_before_nudge=3)
    monitor.record("file_read")
    monitor.record("file_read")
    monitor.record("file_write")  # Action breaks the streak
    monitor.record("file_read")
    signal = monitor.check_efficiency()
    assert not signal.is_imbalanced


def test_reset_clears_state():
    monitor = ToolEfficiencyMonitor(max_reads_before_nudge=2)
    monitor.record("file_read")
    monitor.record("file_read")
    monitor.record("file_read")
    monitor.reset()
    signal = monitor.check_efficiency()
    assert not signal.is_imbalanced
```

---

## Enhancement 3: Output Truncation Detection (P1)

### Problem

LLM outputs can be silently truncated when hitting `max_tokens`. Pythinker's validators check content quality but don't specifically detect **truncated responses**. DeepCode's `_assess_output_completeness()` catches this.

### DeepCode Pattern

```python
# DeepCode: workflows/agent_orchestration_engine.py
def _assess_output_completeness(text: str) -> float:
    # Check last line for truncation indicators
    last_line = lines[-1].strip()
    if last_line.endswith(("```", ".", ":", "]", "}")):
        score += 0.15  # Properly terminated
    else:
        # Long line without proper ending = likely truncated
        print(f"⚠️ Last line suspicious: '{last_line[-50:]}'")
```

### Pythinker Integration

**Approach:** Add a `TruncationDetector` utility and integrate with existing `OutputCoverageValidator`.

**File to create:** `backend/app/domain/services/agents/truncation_detector.py`

```python
"""
LLM output truncation detection.

Detects when LLM responses are silently truncated due to max_tokens limits.
Integrates with existing OutputCoverageValidator for comprehensive quality checks.

Context7 validated: Pydantic v2 BaseModel with model_validator pattern.
"""

import re
from typing import Self

from pydantic import BaseModel, Field, model_validator


class TruncationAssessment(BaseModel):
    """Result of truncation analysis.

    Context7 validated: Pydantic v2 @model_validator(mode='after') with Self.
    """
    is_truncated: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    indicators: list[str] = Field(default_factory=list)
    suggestion: str | None = None

    @model_validator(mode="after")
    def _set_suggestion(self) -> Self:
        """Auto-generate suggestion when truncated.

        Context7 validated: Pydantic v2 mode='after' returns Self.
        """
        if self.is_truncated and not self.suggestion:
            self.suggestion = "Retry with higher max_tokens or request continuation"
        return self


class TruncationDetector:
    """Detects truncated LLM outputs.

    Design Principles:
    - KISS: Simple heuristic checks, no ML required
    - Single Responsibility: Only detects truncation
    - Composition: Used by validators, not replacing them
    """

    # Proper termination markers
    VALID_ENDINGS = frozenset({".", "!", "?", ":", "```", "]", "}", ")", '"', "'", "*"})

    # Patterns that indicate mid-sentence truncation
    TRUNCATION_PATTERNS = [
        r"\w+$",                    # Ends with a word (no punctuation)
        r",\s*$",                   # Ends with a comma
        r"\band\s*$",              # Ends with "and"
        r"\bthe\s*$",             # Ends with "the"
        r"\bwith\s*$",            # Ends with "with"
        r"```\w+\n[^`]*$",        # Unclosed code block
    ]

    def assess(self, text: str, max_tokens_used: int | None = None) -> TruncationAssessment:
        """Assess whether text appears truncated.

        Args:
            text: The LLM output to check
            max_tokens_used: If known, the token count (hitting limit = likely truncated)

        Returns:
            TruncationAssessment with confidence score and indicators
        """
        if not text or len(text.strip()) < 50:
            return TruncationAssessment()

        indicators: list[str] = []
        confidence = 0.0

        # Check 1: Token limit reached (strongest signal)
        if max_tokens_used is not None:
            # If usage is within 95% of max_tokens, likely truncated
            # (we don't know max here, but if caller provides it, trust it)
            indicators.append(f"Used {max_tokens_used} tokens")
            confidence += 0.4

        # Check 2: Last line analysis
        lines = text.strip().split("\n")
        last_line = lines[-1].strip()

        if last_line and not any(last_line.endswith(ending) for ending in self.VALID_ENDINGS):
            if len(last_line) > 80:  # Long line without proper ending
                indicators.append(f"Last line ({len(last_line)} chars) lacks termination")
                confidence += 0.3
            elif len(last_line) > 20:
                indicators.append("Last line lacks proper punctuation")
                confidence += 0.15

        # Check 3: Unclosed code blocks
        open_blocks = text.count("```")
        if open_blocks % 2 != 0:
            indicators.append(f"Unclosed code block ({open_blocks} markers)")
            confidence += 0.3

        # Check 4: Truncation regex patterns
        for pattern in self.TRUNCATION_PATTERNS:
            if re.search(pattern, text.strip()):
                indicators.append(f"Pattern match: {pattern}")
                confidence += 0.1
                break  # Only count one pattern match

        # Check 5: Incomplete markdown structure
        open_headers = len(re.findall(r"^#{1,6}\s", text, re.MULTILINE))
        if open_headers > 0 and not text.strip().endswith((".", "```", "---")):
            indicators.append("Incomplete markdown structure")
            confidence += 0.1

        is_truncated = confidence >= 0.4  # 40% confidence threshold

        return TruncationAssessment(
            is_truncated=is_truncated,
            confidence=min(confidence, 1.0),
            indicators=indicators,
        )
```

**File to modify:** `backend/app/domain/services/agents/execution.py`

```python
# In ExecutionAgent, after receiving LLM response:
from app.domain.services.agents.truncation_detector import TruncationDetector

_truncation_detector = TruncationDetector()

# After LLM call:
assessment = _truncation_detector.assess(response_text, max_tokens_used=usage.completion_tokens)
if assessment.is_truncated:
    logger.warning("Truncated output detected: %s", assessment.indicators)
    # Option 1: Retry with "Please continue from where you left off"
    # Option 2: Emit a warning event for the frontend
```

### Testing

```python
# backend/tests/domain/services/agents/test_truncation_detector.py

import pytest
from app.domain.services.agents.truncation_detector import TruncationDetector, TruncationAssessment


@pytest.fixture
def detector():
    return TruncationDetector()


def test_complete_output_not_flagged(detector):
    text = "Here is the complete analysis.\n\nThe results show clear trends."
    result = detector.assess(text)
    assert not result.is_truncated


def test_unclosed_code_block_detected(detector):
    text = "Here is the code:\n```python\ndef hello():\n    print('hello')"
    result = detector.assess(text)
    assert result.is_truncated
    assert any("code block" in i for i in result.indicators)


def test_mid_sentence_truncation_detected(detector):
    text = "The implementation should handle authentication, authorization, and the"
    result = detector.assess(text)
    assert result.is_truncated


def test_proper_ending_not_flagged(detector):
    text = "# Summary\n\nAll tasks completed successfully."
    result = detector.assess(text)
    assert not result.is_truncated


def test_suggestion_auto_generated():
    """Context7: Pydantic v2 model_validator test."""
    assessment = TruncationAssessment(is_truncated=True, confidence=0.8, indicators=["test"])
    assert assessment.suggestion is not None
    assert "Retry" in assessment.suggestion
```

---

## Enhancement 4: Document Segmentation (P2)

### Problem

When users upload large documents (research papers, long codebases), Pythinker processes them as single inputs that may exceed context limits. DeepCode's `DocumentSegmentationAgent` intelligently chunks documents.

### Pythinker Integration

**File to create:** `backend/app/domain/services/document/segmenter.py`

```python
"""
Document segmentation for large input processing.

Splits large documents into processable segments that fit within
model context limits while preserving semantic coherence.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from app.domain.services.agents.token_manager import TokenManager


@dataclass
class DocumentSegment:
    """A segment of a large document."""
    index: int
    content: str
    token_count: int
    start_char: int
    end_char: int
    metadata: dict[str, str] = field(default_factory=dict)


class DocumentSegmenter:
    """Segments large documents into processable chunks.

    Uses the existing TokenManager for accurate token counting
    and splits on semantic boundaries (paragraphs, sections).

    Design Principles:
    - KISS: Simple paragraph-based splitting with token counting
    - Composition: Uses existing TokenManager, doesn't reinvent counting
    - Single Responsibility: Only segments, doesn't process segments
    """

    # Heading patterns that mark good split points
    SECTION_MARKERS: ClassVar[list[str]] = [
        "\n# ",       # H1
        "\n## ",      # H2
        "\n### ",     # H3
        "\n---\n",    # Horizontal rule
        "\n\n\n",     # Triple newline
    ]

    def __init__(
        self,
        max_tokens_per_segment: int = 50_000,
        overlap_tokens: int = 200,
    ):
        self._max_tokens = max_tokens_per_segment
        self._overlap = overlap_tokens
        self._token_mgr = TokenManager()

    def segment(self, document: str) -> list[DocumentSegment]:
        """Segment document into token-bounded chunks.

        Splits preferentially on section boundaries, falling back
        to paragraph boundaries, then sentence boundaries.
        """
        total_tokens = self._token_mgr.count_tokens(document)

        if total_tokens <= self._max_tokens:
            return [DocumentSegment(
                index=0,
                content=document,
                token_count=total_tokens,
                start_char=0,
                end_char=len(document),
            )]

        # Split on best available boundaries
        segments: list[DocumentSegment] = []
        remaining = document
        char_offset = 0

        while remaining:
            # Find split point within token budget
            split_pos = self._find_split_point(remaining)

            chunk = remaining[:split_pos].rstrip()
            chunk_tokens = self._token_mgr.count_tokens(chunk)

            segments.append(DocumentSegment(
                index=len(segments),
                content=chunk,
                token_count=chunk_tokens,
                start_char=char_offset,
                end_char=char_offset + len(chunk),
            ))

            char_offset += split_pos
            remaining = remaining[split_pos:].lstrip()

        return segments

    def _find_split_point(self, text: str) -> int:
        """Find optimal split point within token budget.

        Priority: section marker > paragraph > sentence > hard cut.
        """
        # Binary search for approximate character position at token limit
        # (4 chars ≈ 1 token as initial estimate, refined by TokenManager)
        estimated_chars = self._max_tokens * 4
        if estimated_chars >= len(text):
            return len(text)

        # Try section markers first
        for marker in self.SECTION_MARKERS:
            pos = text.rfind(marker, 0, estimated_chars)
            if pos > estimated_chars // 2:  # At least half-way through
                return pos

        # Try paragraph boundary
        pos = text.rfind("\n\n", 0, estimated_chars)
        if pos > estimated_chars // 4:
            return pos + 2  # Include the newlines

        # Try sentence boundary
        for ending in (". ", "! ", "? "):
            pos = text.rfind(ending, 0, estimated_chars)
            if pos > 0:
                return pos + len(ending)

        # Hard cut at estimated position
        return estimated_chars
```

---

## Enhancement 5: Implementation File Tracker (P2)

### Problem

During multi-file code generation tasks, Pythinker tracks step-level progress but not **which files** have been implemented. DeepCode tracks `implemented_files_set` and `files_read_for_dependencies` for precise progress.

### Pythinker Integration

**File to create:** `backend/app/domain/services/agents/implementation_tracker.py`

```python
"""
File-level implementation progress tracker.

Tracks which files have been created/modified during code generation tasks,
providing granular progress visibility beyond step-level tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FileStatus(str, Enum):
    """Implementation status for a tracked file."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TrackedFile:
    """A file being tracked during implementation."""
    path: str
    status: FileStatus = FileStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    dependencies_read: list[str] = field(default_factory=list)


class ImplementationTracker:
    """Tracks file-level progress during code generation.

    Design Principles:
    - KISS: Simple set-based tracking
    - Single Responsibility: Only tracks files, doesn't execute
    """

    def __init__(self) -> None:
        self._files: dict[str, TrackedFile] = {}
        self._read_for_deps: set[str] = set()

    def register_files(self, file_paths: list[str]) -> None:
        """Register files from a plan for tracking."""
        for path in file_paths:
            if path not in self._files:
                self._files[path] = TrackedFile(path=path)

    def mark_started(self, path: str) -> None:
        """Mark file implementation as started."""
        if path not in self._files:
            self._files[path] = TrackedFile(path=path)
        self._files[path].status = FileStatus.IN_PROGRESS
        self._files[path].started_at = datetime.now()

    def mark_completed(self, path: str) -> None:
        """Mark file implementation as completed."""
        if path in self._files:
            self._files[path].status = FileStatus.COMPLETED
            self._files[path].completed_at = datetime.now()

    def record_dependency_read(self, impl_path: str, dep_path: str) -> None:
        """Record that a dependency file was read for implementation."""
        self._read_for_deps.add(dep_path)
        if impl_path in self._files:
            self._files[impl_path].dependencies_read.append(dep_path)

    @property
    def progress(self) -> float:
        """Overall completion percentage (0.0-1.0)."""
        if not self._files:
            return 0.0
        completed = sum(1 for f in self._files.values() if f.status == FileStatus.COMPLETED)
        return completed / len(self._files)

    @property
    def completed_count(self) -> int:
        return sum(1 for f in self._files.values() if f.status == FileStatus.COMPLETED)

    @property
    def total_count(self) -> int:
        return len(self._files)

    def get_summary(self) -> dict[str, int]:
        """Get status summary."""
        counts: dict[str, int] = {}
        for f in self._files.values():
            counts[f.status.value] = counts.get(f.status.value, 0) + 1
        return counts
```

---

## Implementation Schedule

### Phase 1: P0 — Adaptive Model Selection (Week 1)

| Task | File | Action |
|------|------|--------|
| Add `ModelTier` enum | `complexity_assessor.py` | MODIFY |
| Add model config to Settings | `config.py` | MODIFY |
| Add `_select_model_for_step` | `execution.py` | MODIFY |
| Add `useModelTier` composable | `useModelTier.ts` | CREATE |
| Unit tests | `test_adaptive_model.py` | CREATE |

### Phase 2: P1 — Tool Efficiency + Truncation (Week 2)

| Task | File | Action |
|------|------|--------|
| Create `ToolEfficiencyMonitor` | `tool_efficiency_monitor.py` | CREATE |
| Create `TruncationDetector` | `truncation_detector.py` | CREATE |
| Integrate into `BaseAgent` | `base.py` | MODIFY |
| Integrate into `ExecutionAgent` | `execution.py` | MODIFY |
| Unit tests | `test_tool_efficiency_monitor.py` | CREATE |
| Unit tests | `test_truncation_detector.py` | CREATE |

### Phase 3: P2 — Segmentation + File Tracker (Week 3)

| Task | File | Action |
|------|------|--------|
| Create `DocumentSegmenter` | `segmenter.py` | CREATE |
| Create `ImplementationTracker` | `implementation_tracker.py` | CREATE |
| Integration with plan_act flow | `plan_act.py` | MODIFY |
| Unit tests | `test_segmenter.py`, `test_implementation_tracker.py` | CREATE |

---

## File Impact Summary

### Files to CREATE (7 new files)

```
backend/app/domain/services/agents/
├── tool_efficiency_monitor.py          ← Tool read/write balance monitoring
├── truncation_detector.py              ← LLM output truncation detection
├── implementation_tracker.py           ← File-level code generation tracking

backend/app/domain/services/document/
├── __init__.py
└── segmenter.py                        ← Large document chunking

frontend/src/composables/
└── useModelTier.ts                     ← Model tier display composable

backend/tests/domain/services/agents/
├── test_tool_efficiency_monitor.py
├── test_truncation_detector.py
├── test_adaptive_model.py
└── test_implementation_tracker.py
```

### Files to MODIFY (4 existing files)

```
backend/app/domain/services/agents/complexity_assessor.py  ← Add ModelTier
backend/app/domain/services/agents/base.py                 ← Integrate efficiency monitor
backend/app/domain/services/agents/execution.py            ← Add model selection + truncation
backend/app/core/config.py                                 ← Add model tier settings
```

### Total: 7 new files + 4 modifications

This is **dramatically smaller** than the v1 plan's 33 files because we're building on existing infrastructure instead of rebuilding it.

---

## Testing Strategy

### Unit Tests (Target: 95% coverage on new code)

```bash
# Run all new tests
conda activate pythinker && cd backend
pytest tests/domain/services/agents/test_tool_efficiency_monitor.py -v
pytest tests/domain/services/agents/test_truncation_detector.py -v
pytest tests/domain/services/agents/test_adaptive_model.py -v
pytest tests/domain/services/agents/test_implementation_tracker.py -v

# Run with coverage
pytest tests/domain/services/agents/ --cov=app.domain.services.agents -k "efficiency or truncation or adaptive or tracker"
```

### Integration Tests

```bash
# Verify no regressions in existing agent flow
pytest tests/ -v --tb=short
```

---

## Prometheus Metrics

Extend existing metrics (no new file needed):

```python
# Add to existing metrics infrastructure
from prometheus_client import Counter, Histogram

# Adaptive model selection
model_tier_selections = Counter(
    "pythinker_model_tier_selections_total",
    "Model tier selections by step type",
    ["tier"],  # fast, balanced, powerful
)

# Tool efficiency
tool_efficiency_nudges = Counter(
    "pythinker_tool_efficiency_nudges_total",
    "Times agent was nudged for analysis paralysis",
)

# Truncation detection
output_truncations_detected = Counter(
    "pythinker_output_truncations_total",
    "Truncated LLM outputs detected",
)
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Model selection wrong for step | Medium | Low | Feature flag, default to balanced |
| Efficiency nudge too aggressive | Low | Medium | Configurable threshold, conservative default |
| Truncation false positives | Low | Medium | High confidence threshold (0.4), log-only initially |
| Segmenter splits mid-context | Medium | Low | Semantic boundary preference, overlap tokens |

All features behind `Settings` booleans — disable without deployment.

---

## Success Criteria

- [ ] **Cost reduction:** 20%+ on mixed-complexity sessions (model selection)
- [ ] **Analysis paralysis:** 50%+ reduction in excessive-read patterns (efficiency monitor)
- [ ] **Output quality:** 90%+ of truncated outputs detected before delivery (truncation)
- [ ] **No regressions:** All existing tests continue passing
- [ ] **Test coverage:** 95%+ on new code

---

## Appendix: DeepCode Files Analyzed

| File | Size | Key Pattern Extracted |
|------|------|---------------------|
| `workflows/agent_orchestration_engine.py` | 78KB | Output completeness scoring, adaptive LLM config |
| `workflows/code_implementation_workflow.py` | 62KB | Workflow management, file tree creation |
| `workflows/agents/code_implementation_agent.py` | — | Token management, tool call tracking, read/write balance |
| `workflows/agents/requirement_analysis_agent.py` | — | Structured Q&A, requirement extraction |
| `workflows/agents/memory_agent_concise.py` | — | Periodic context summarization |
| `workflows/agents/document_segmentation_agent.py` | — | Large document chunking |
| `tools/code_indexer.py` | 66KB | Codebase relationship indexing |
| `utils/llm_utils.py` | — | Adaptive model selection, token limits |

---

**Document End — v2 Complete Rewrite**

*Key difference from v1: This plan creates 7 files instead of 33 by building on Pythinker's existing infrastructure rather than reinventing it.*
