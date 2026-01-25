# Performance Optimization Implementation Strategy

**Date:** January 24, 2026
**Project:** Pythinker AI Agent System
**Version:** 1.0

---

## Executive Summary

This document provides a detailed implementation strategy for optimizing the Pythinker agent system across three key dimensions:
1. **Speed Optimization** - Reducing latency and improving throughput
2. **Hallucination Reduction** - Ensuring accuracy and reliability
3. **Intelligence Enhancement** - Improving reasoning and context awareness

Each section includes specific code locations, implementation details, and expected impact.

---

## Table of Contents

1. [Speed Optimization Strategies](#1-speed-optimization-strategies)
2. [Hallucination Reduction Mechanisms](#2-hallucination-reduction-mechanisms)
3. [Intelligence & Context Awareness Enhancement](#3-intelligence--context-awareness-enhancement)
4. [Implementation Priority Matrix](#4-implementation-priority-matrix)
5. [Code-Level Modifications](#5-code-level-modifications)

---

## 1. Speed Optimization Strategies

### 1.1 Prompt Caching Implementation

**Current State:** Caching infrastructure exists but not fully utilized.

**Files to Modify:**
- `backend/app/infrastructure/external/llm/anthropic_llm.py` (lines 266-289)
- `backend/app/infrastructure/external/llm/openai_llm.py` (lines 346, 479)
- `backend/app/domain/services/agents/base.py` (lines 339-342)

**Implementation:**

```python
# backend/app/infrastructure/external/llm/anthropic_llm.py

async def ask(
    self,
    system_prompt: str,
    user_message: str,
    enable_caching: bool = True,  # Default to enabled
    **kwargs
) -> str:
    """Send request with prompt caching enabled."""

    # Prepare messages with cache control
    messages = self._prepare_messages_with_caching(
        system_prompt, user_message, enable_caching
    )

    params = {
        "model": self.model,
        "max_tokens": kwargs.get("max_tokens", 4096),
        "messages": messages,
    }

    # Add beta header for caching
    if enable_caching:
        params["extra_headers"] = {
            "anthropic-beta": "prompt-caching-2024-07-31"
        }

    response = await self.client.messages.create(**params)
    return response.content[0].text

def _prepare_messages_with_caching(
    self,
    system_prompt: str,
    user_message: str,
    enable_caching: bool
) -> List[Dict]:
    """Structure messages for optimal cache hits."""
    messages = []

    # System prompt with cache control
    if enable_caching:
        messages.append({
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        })
    else:
        messages.append({
            "role": "system",
            "content": system_prompt
        })

    # User message (dynamic, not cached)
    messages.append({
        "role": "user",
        "content": user_message
    })

    return messages
```

**Expected Impact:** Up to 90% token cost reduction on system prompts.

### 1.2 Parallel Tool Execution Enhancement

**Current State:** Limited to static whitelist of 7 safe tools, max 3 concurrent.

**File:** `backend/app/domain/services/agents/base.py` (lines 28-40, 175-230)

**Enhanced Implementation:**

```python
# backend/app/domain/services/agents/base.py

# Expanded safe parallel tools with categories
SAFE_PARALLEL_TOOLS = {
    # Read-only operations
    "info_search_web",
    "file_read",
    "file_search",
    "file_list_directory",
    "browser_get_content",
    "browser_view",
    "browser_screenshot",
    # MCP read-only tools (dynamic detection)
    "mcp_get_*",
    "mcp_list_*",
    "mcp_search_*",
}

# Increase concurrent limit for read-heavy workloads
MAX_CONCURRENT_TOOLS = 5  # Was 3

# Dynamic parallelization based on context
def _can_parallelize_tools(self, tool_calls: List[ToolCall]) -> bool:
    """Determine if tool calls can be parallelized."""
    # Quick path: all tools in safe list
    all_safe = all(
        any(
            tc.function.name == safe or
            (safe.endswith('*') and tc.function.name.startswith(safe[:-1]))
            for safe in SAFE_PARALLEL_TOOLS
        )
        for tc in tool_calls
    )

    if all_safe:
        return True

    # Advanced: check for resource conflicts
    return self._analyze_tool_dependencies(tool_calls)

def _analyze_tool_dependencies(self, tool_calls: List[ToolCall]) -> bool:
    """Analyze if tool calls have resource conflicts."""
    resources_accessed = set()

    for tc in tool_calls:
        # Extract resource paths from arguments
        args = json.loads(tc.function.arguments)

        if 'file' in args or 'path' in args:
            path = args.get('file') or args.get('path')
            if path in resources_accessed:
                return False  # Conflict detected
            resources_accessed.add(path)

    return True  # No conflicts, can parallelize
```

**Expected Impact:** 30-40% latency reduction for multi-tool operations.

### 1.3 Token Counting Optimization

**Current State:** Token counting repeated on same messages.

**File:** `backend/app/domain/services/agents/token_manager.py` (lines 226-244)

**Implementation:**

```python
# backend/app/domain/services/agents/token_manager.py

from functools import lru_cache
import hashlib

class TokenManager:
    def __init__(self):
        self._message_token_cache: Dict[str, int] = {}

    def count_messages_tokens(self, messages: List[Message]) -> int:
        """Count tokens with per-message caching."""
        total = 0

        for msg in messages:
            cache_key = self._message_cache_key(msg)

            if cache_key in self._message_token_cache:
                total += self._message_token_cache[cache_key]
            else:
                count = self.count_message_tokens(msg)
                self._message_token_cache[cache_key] = count
                total += count

        return total

    def _message_cache_key(self, msg: Message) -> str:
        """Generate stable cache key for message."""
        content = f"{msg.role}:{msg.content[:1000]}"  # First 1000 chars
        return hashlib.md5(content.encode()).hexdigest()

    def invalidate_cache(self):
        """Clear token cache when messages are modified."""
        self._message_token_cache.clear()
```

**Expected Impact:** 5-10% latency reduction on context management.

### 1.4 Multi-Tier Caching Architecture

**Current State:** Single Redis layer.

**Implementation:**

```python
# backend/app/domain/services/tools/multi_tier_cache.py

from collections import OrderedDict
import gzip
import json

class L1Cache:
    """In-memory LRU cache for hot data."""

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self.cache = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: Any):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)
        self.cache[key] = value


class MultiTierCache:
    """L1 (memory) -> L2 (Redis) cache hierarchy."""

    def __init__(self, redis_client, config: CacheConfig):
        self.l1 = L1Cache(max_size=config.l1_max_size)
        self.l2 = redis_client
        self.compression_threshold = 5000  # Compress if > 5KB

    async def get(self, key: str) -> Optional[Any]:
        # Try L1 first
        value = self.l1.get(key)
        if value is not None:
            return value

        # Try L2
        raw = await self.l2.get(key)
        if raw is None:
            return None

        # Decompress if needed
        value = self._decompress(raw)

        # Promote to L1
        self.l1.set(key, value)

        return value

    async def set(self, key: str, value: Any, ttl: int = 3600):
        # Set in L1
        self.l1.set(key, value)

        # Compress and set in L2
        raw = self._compress(value)
        await self.l2.setex(key, ttl, raw)

    def _compress(self, value: Any) -> bytes:
        """Compress large values."""
        data = json.dumps(value).encode()
        if len(data) > self.compression_threshold:
            return b'gz:' + gzip.compress(data)
        return data

    def _decompress(self, raw: bytes) -> Any:
        """Decompress if needed."""
        if raw.startswith(b'gz:'):
            data = gzip.decompress(raw[3:])
        else:
            data = raw
        return json.loads(data)
```

**Expected Impact:** 40-50% latency reduction for repeated queries, 60% storage reduction via compression.

### 1.5 Cache Warmup Strategy

**Implementation:**

```python
# backend/app/application/services/cache_warmer.py

class CacheWarmer:
    """Pre-warm caches during system startup."""

    def __init__(self, cache: MultiTierCache, llm_client, redis_client):
        self.cache = cache
        self.llm = llm_client
        self.redis = redis_client

    async def warm_on_startup(self):
        """Run cache warmup tasks."""
        await asyncio.gather(
            self._warm_system_prompts(),
            self._warm_common_searches(),
            self._warm_tool_schemas(),
        )

    async def _warm_system_prompts(self):
        """Pre-cache system prompts for KV cache efficiency."""
        from app.domain.services.prompts.system import CORE_PROMPT

        # Make dummy request to establish cache
        try:
            await self.llm.ask(
                system_prompt=CORE_PROMPT,
                user_message="Hello",
                enable_caching=True,
                max_tokens=10
            )
            logger.info("System prompt cache warmed")
        except Exception as e:
            logger.warning(f"Cache warmup failed: {e}")

    async def _warm_common_searches(self):
        """Pre-cache common search queries."""
        common_queries = await self.redis.lrange("common_searches", 0, 100)
        for query in common_queries:
            # Trigger search to populate cache
            pass

    async def _warm_tool_schemas(self):
        """Pre-cache MCP tool schemas."""
        from app.domain.services.tools.mcp import MCPClientManager
        manager = MCPClientManager()
        await manager.get_all_tools()  # Populates internal cache
```

---

## 2. Hallucination Reduction Mechanisms

### 2.1 Pre-Delivery Fact Check

**Current State:** Only post-hoc detection via Critic agent.

**File:** `backend/app/domain/services/agents/execution.py`

**Implementation:**

```python
# backend/app/domain/services/prompts/verification.py

FACT_CHECK_PROMPT = """
Before finalizing this output, verify each claim:

For each factual statement in your response:
1. Did I retrieve this from a source?
   - YES: Include citation [N]
   - NO: Mark as [unverified] or remove

2. Did multiple sources agree?
   - YES: Cite primary source
   - NO: Note the disagreement

3. Is this time-sensitive information?
   - YES: Verify data recency
   - NO: No additional check needed

Review your output with these checks applied.
Do not include claims you cannot verify.
"""

# backend/app/domain/services/agents/execution.py

async def _fact_check_response(self, response: str, context: ExecutionContext) -> str:
    """Run fact-check on research responses before delivery."""

    if not self._is_research_task(context.original_request):
        return response

    fact_check_messages = [
        {"role": "system", "content": FACT_CHECK_PROMPT},
        {"role": "user", "content": f"Review and verify:\n\n{response}"}
    ]

    verified_response = await self.llm.ask(
        system_prompt=FACT_CHECK_PROMPT,
        user_message=f"Review and verify:\n\n{response}",
        max_tokens=len(response) * 2  # Allow expansion for citations
    )

    return verified_response
```

**Expected Impact:** 60-70% reduction in uncited claims.

### 2.2 Tool Hallucination Detection

**Current State:** Invalid tool calls raise generic errors.

**File:** `backend/app/domain/services/agents/base.py` (lines 82-87)

**Implementation:**

```python
# backend/app/domain/services/agents/base.py

class ToolHallucinationDetector:
    def __init__(self, available_tools: List[str]):
        self.available_tools = set(available_tools)
        self.hallucination_count = 0
        self.hallucination_threshold = 3

    def detect(self, tool_name: str) -> Optional[str]:
        """Detect and suggest correction for hallucinated tool."""
        if tool_name in self.available_tools:
            return None

        self.hallucination_count += 1

        # Find similar tools
        similar = self._find_similar_tools(tool_name)

        if similar:
            return f"Tool '{tool_name}' does not exist. Did you mean: {', '.join(similar)}?"

        return f"Tool '{tool_name}' does not exist. Available tools: {', '.join(sorted(self.available_tools)[:10])}"

    def _find_similar_tools(self, name: str, threshold: float = 0.6) -> List[str]:
        """Find tools with similar names."""
        from difflib import SequenceMatcher

        similar = []
        for tool in self.available_tools:
            ratio = SequenceMatcher(None, name.lower(), tool.lower()).ratio()
            if ratio >= threshold:
                similar.append(tool)

        return sorted(similar, key=lambda t: SequenceMatcher(None, name, t).ratio(), reverse=True)[:3]

    def should_inject_correction(self) -> bool:
        """Check if correction prompt should be injected."""
        return self.hallucination_count >= self.hallucination_threshold


# Integration in base.py invoke_tool():
async def invoke_tool(self, function_name: str, arguments: Dict) -> ToolResult:
    """Invoke tool with hallucination detection."""

    # Check for hallucination
    correction = self.hallucination_detector.detect(function_name)
    if correction:
        logger.warning(f"Tool hallucination detected: {function_name}")
        return ToolResult(
            success=False,
            error=correction,
            data=None
        )

    # Proceed with normal execution
    tool = self.get_tool(function_name)
    return await tool.invoke_function(function_name, **arguments)
```

**Expected Impact:** Immediate detection and correction of invalid tool calls.

### 2.3 Confidence Scoring

**Implementation:**

```python
# backend/app/domain/services/agents/confidence_scorer.py

from dataclasses import dataclass
from typing import List

@dataclass
class ConfidenceScore:
    overall: float  # 0.0 - 1.0
    source_coverage: float  # % of claims with sources
    consistency: float  # Agreement across sources
    recency: float  # How recent the sources are
    reasoning: str  # Explanation

class ConfidenceScorer:
    """Score confidence in agent responses."""

    async def score(self, response: str, sources: List[Source]) -> ConfidenceScore:
        """Calculate confidence score for response."""

        # Count claims and citations
        claims = self._extract_claims(response)
        citations = self._extract_citations(response)

        source_coverage = len(citations) / max(len(claims), 1)

        # Check source consistency
        consistency = self._check_consistency(sources)

        # Check recency
        recency = self._check_recency(sources)

        # Overall score
        overall = (
            source_coverage * 0.4 +
            consistency * 0.3 +
            recency * 0.2 +
            0.1  # Base confidence
        )

        return ConfidenceScore(
            overall=min(overall, 1.0),
            source_coverage=source_coverage,
            consistency=consistency,
            recency=recency,
            reasoning=self._generate_reasoning(source_coverage, consistency, recency)
        )

    def _extract_claims(self, text: str) -> List[str]:
        """Extract factual claims from text."""
        # Simple heuristic: sentences with numbers or definitive statements
        import re
        sentences = re.split(r'[.!?]', text)
        claims = [s for s in sentences if re.search(r'\d+|always|never|is|are|was|were', s, re.I)]
        return claims

    def _extract_citations(self, text: str) -> List[str]:
        """Extract citation markers from text."""
        import re
        return re.findall(r'\[(\d+)\]', text)

    def _check_consistency(self, sources: List[Source]) -> float:
        """Check if sources agree with each other."""
        if len(sources) < 2:
            return 0.5  # Neutral if single source
        # Implementation: compare key facts across sources
        return 0.8  # Placeholder

    def _check_recency(self, sources: List[Source]) -> float:
        """Score based on source recency."""
        if not sources:
            return 0.0

        from datetime import datetime, timedelta
        now = datetime.now()
        six_months = timedelta(days=180)

        recent_count = sum(1 for s in sources if (now - s.date) < six_months)
        return recent_count / len(sources)
```

**Expected Impact:** Explicit confidence signals help users gauge reliability.

### 2.4 Critic Improvement - Structured Feedback

**Current State:** Critic provides only APPROVE/REVISE/REJECT.

**File:** `backend/app/domain/services/agents/critic.py`

**Implementation:**

```python
# backend/app/domain/services/prompts/critic.py

STRUCTURED_CRITIC_PROMPT = """
Review this output and provide structured feedback.

For each issue found, specify:
1. Issue Type: [missing_citation | factual_error | outdated_info | incomplete | format_error]
2. Location: Quote the problematic text
3. Severity: [critical | major | minor]
4. Suggested Fix: Specific correction

Example:
{
  "decision": "REVISE",
  "issues": [
    {
      "type": "missing_citation",
      "location": "Python 3.12 was released in October 2023",
      "severity": "major",
      "fix": "Add citation: [1] https://python.org/downloads/release/python-3120/"
    }
  ],
  "summary": "Good structure but needs source citations for release dates."
}

Output JSON only.
"""

# backend/app/domain/models/critic.py

from pydantic import BaseModel
from typing import List, Literal

class CriticIssue(BaseModel):
    type: Literal["missing_citation", "factual_error", "outdated_info", "incomplete", "format_error"]
    location: str
    severity: Literal["critical", "major", "minor"]
    fix: str

class CriticReview(BaseModel):
    decision: Literal["APPROVE", "REVISE", "REJECT"]
    issues: List[CriticIssue]
    summary: str
```

**Expected Impact:** 30-40% reduction in revision iterations due to actionable feedback.

---

## 3. Intelligence & Context Awareness Enhancement

### 3.1 Execution Chain-of-Thought

**Current State:** Execution jumps directly to tool calls without explicit reasoning.

**Implementation:**

```python
# backend/app/domain/services/prompts/execution.py

EXECUTION_COT_PROMPT = """
Before executing this step, reason through your approach:

Current Step: {step}
Available Tools: {tools}

Think through:
1. Goal: What specifically needs to be accomplished?
2. Information: What do I already know? What do I need to find out?
3. Approach: Which tool(s) will help? In what order?
4. Risks: What could go wrong? How will I detect failure?
5. Verification: How will I know this step succeeded?

After reasoning, execute with confidence.
"""

# backend/app/domain/services/agents/execution.py

async def execute_step_with_cot(self, step: PlanStep, context: ExecutionContext) -> StepResult:
    """Execute step with chain-of-thought reasoning."""

    # Only use CoT for complex steps
    if self._is_complex_step(step):
        cot_prompt = EXECUTION_COT_PROMPT.format(
            step=step.description,
            tools=', '.join(self._get_relevant_tools(step))
        )

        # Get reasoning first
        reasoning = await self.llm.ask(
            system_prompt=self.system_prompt,
            user_message=cot_prompt,
            max_tokens=500
        )

        # Log reasoning for debugging
        logger.debug(f"Step reasoning: {reasoning}")

        # Now execute with reasoning context
        execution_prompt = f"{cot_prompt}\n\nMy reasoning:\n{reasoning}\n\nNow execute."
    else:
        execution_prompt = f"Execute: {step.description}"

    # Continue with tool execution
    return await self._execute_with_prompt(execution_prompt, context)

def _is_complex_step(self, step: PlanStep) -> bool:
    """Determine if step warrants explicit reasoning."""
    complexity_indicators = [
        len(step.description) > 100,
        "multiple" in step.description.lower(),
        "compare" in step.description.lower(),
        "analyze" in step.description.lower(),
        step.dependencies and len(step.dependencies) > 1,
    ]
    return sum(complexity_indicators) >= 2
```

**Expected Impact:** 10-15% improvement in first-pass success rate for complex steps.

### 3.2 Memory Context Schema

**Current State:** Memory injected as unstructured text.

**Implementation:**

```python
# backend/app/domain/services/memory/memory_formatter.py

MEMORY_CONTEXT_TEMPLATE = """
---
RELEVANT PAST EXPERIENCE:

{memory_items}

Apply these learnings to your current task.
---
"""

MEMORY_ITEM_TEMPLATE = """
- [{memory_type}] {summary}
  Context: {context}
  Outcome: {outcome}
"""

class MemoryFormatter:
    """Format memories for structured context injection."""

    def __init__(self, max_tokens: int = 500):
        self.max_tokens = max_tokens

    def format_memories(self, memories: List[Memory]) -> Optional[str]:
        """Format memories with schema."""
        if not memories:
            return None

        items = []
        token_count = 0
        token_budget = self.max_tokens - 50  # Reserve for template

        for mem in memories:
            formatted = MEMORY_ITEM_TEMPLATE.format(
                memory_type=mem.type.upper(),
                summary=mem.summary[:200],
                context=mem.context[:100] if mem.context else "N/A",
                outcome=mem.outcome[:100] if mem.outcome else "N/A"
            )

            tokens = len(formatted) // 4
            if token_count + tokens > token_budget:
                break

            items.append(formatted)
            token_count += tokens

        if not items:
            return None

        return MEMORY_CONTEXT_TEMPLATE.format(
            memory_items="\n".join(items)
        )
```

### 3.3 Adaptive Prompt Injection

**Current State:** PromptAdapter triggers only ~20% of the time.

**File:** `backend/app/domain/services/agents/prompt_adapter.py`

**Enhancement:**

```python
# backend/app/domain/services/agents/prompt_adapter.py

class EnhancedPromptAdapter:
    """More aggressive context-aware prompt adaptation."""

    def should_inject_guidance(self, context: AdaptationContext) -> bool:
        """More frequent guidance injection."""
        # Always inject on errors
        if context.recent_errors:
            return True

        # Inject at iteration thresholds
        if context.iteration_count in [5, 10, 15, 20, 25, 30]:
            return True

        # Inject for specialized contexts every 3 iterations
        if context.primary_context != ContextType.GENERAL:
            return context.iteration_count % 3 == 0

        # Inject every 5 iterations for general context
        return context.iteration_count % 5 == 0

    def get_error_recovery_prompt(self, errors: List[str], error_types: List[str]) -> str:
        """Generate specific error recovery guidance."""
        unique_types = set(error_types)

        prompts = []
        for error_type in unique_types:
            if error_type == "TOOL_NOT_FOUND":
                prompts.append("Verify tool names exactly match available tools.")
            elif error_type == "TIMEOUT":
                prompts.append("Consider breaking the operation into smaller steps.")
            elif error_type == "PERMISSION_DENIED":
                prompts.append("Check if the operation requires elevated permissions.")
            elif error_type == "PARSE_ERROR":
                prompts.append("Ensure output format matches expected schema.")

        return "\n".join(prompts)
```

### 3.4 Structured Error Recovery

**Implementation:**

```python
# backend/app/domain/services/prompts/error_recovery.py

ERROR_RECOVERY_PROMPT = """
The last action failed with: {error}

Previous failed attempts:
{error_history}

Instead of repeating the same approach, consider:
1. Different tool or method?
2. Missing prerequisite (API key, permissions, data)?
3. Misunderstanding about the environment?
4. Need to ask user for clarification?

Choose a DIFFERENT approach or escalate to user.
"""

# backend/app/domain/services/agents/execution.py

async def handle_repeated_error(self, error: str, context: ExecutionContext) -> str:
    """Handle errors that have occurred multiple times."""

    error_history = self._format_error_history(context.error_history)

    recovery_prompt = ERROR_RECOVERY_PROMPT.format(
        error=error,
        error_history=error_history
    )

    # Ask for alternative approach
    alternative = await self.llm.ask(
        system_prompt=self.system_prompt + "\n\n" + recovery_prompt,
        user_message="What alternative approach should I try?",
        max_tokens=500
    )

    return alternative
```

**Expected Impact:** 30% reduction in stuck-in-loop iterations.

---

## 4. Implementation Priority Matrix

### Tier 1: Critical (Week 1)

| Task | File | Impact | Effort |
|------|------|--------|--------|
| Enable Anthropic prompt caching | `anthropic_llm.py` | 90% token savings | Low |
| Add tool hallucination detection | `base.py` | Error prevention | Low |
| Expand parallel tool whitelist | `base.py` | 30% latency reduction | Low |

### Tier 2: High Impact (Week 2)

| Task | File | Impact | Effort |
|------|------|--------|--------|
| Pre-delivery fact checking | `execution.py` | 60% citation improvement | Medium |
| Execution CoT for complex steps | `execution.py` | 15% success improvement | Medium |
| Token count caching | `token_manager.py` | 10% latency reduction | Low |

### Tier 3: Medium Impact (Week 3)

| Task | File | Impact | Effort |
|------|------|--------|--------|
| Multi-tier caching | `multi_tier_cache.py` | 40% cache performance | Medium |
| Structured critic feedback | `critic.py` | 30% fewer revisions | Medium |
| Memory context schema | `memory_formatter.py` | Better context usage | Low |

### Tier 4: Polish (Week 4)

| Task | File | Impact | Effort |
|------|------|--------|--------|
| Cache warmup on startup | `cache_warmer.py` | Faster cold start | Medium |
| Confidence scoring | `confidence_scorer.py` | User trust | Medium |
| Adaptive prompt injection | `prompt_adapter.py` | Better guidance | Low |

---

## 5. Code-Level Modifications

### 5.1 Files to Create

| File | Purpose |
|------|---------|
| `backend/app/domain/services/tools/multi_tier_cache.py` | L1/L2 caching |
| `backend/app/domain/services/agents/hallucination_detector.py` | Tool hallucination detection |
| `backend/app/domain/services/agents/confidence_scorer.py` | Response confidence scoring |
| `backend/app/domain/services/prompts/verification.py` | Fact-check prompts |
| `backend/app/domain/services/prompts/error_recovery.py` | Error recovery prompts |
| `backend/app/domain/services/memory/memory_formatter.py` | Structured memory formatting |
| `backend/app/application/services/cache_warmer.py` | Cache pre-warming |

### 5.2 Files to Modify

| File | Lines | Modification |
|------|-------|--------------|
| `anthropic_llm.py` | 266-289 | Add cache control headers |
| `openai_llm.py` | 346, 479 | Integrate cache manager |
| `base.py` | 28-40 | Expand parallel tools |
| `base.py` | 82-87 | Add hallucination detection |
| `base.py` | 339-342 | Use prepared cached messages |
| `token_manager.py` | 226-244 | Add per-message cache |
| `execution.py` | 111-141 | Add fact-check step |
| `critic.py` | Full | Structured feedback |
| `prompt_adapter.py` | Full | More frequent injection |

### 5.3 Configuration Changes

```python
# backend/app/core/config.py

class OptimizationConfig(BaseSettings):
    # Caching
    enable_prompt_caching: bool = True
    l1_cache_max_size: int = 500
    l2_cache_ttl: int = 3600
    compression_threshold: int = 5000

    # Parallelization
    max_concurrent_tools: int = 5
    enable_dynamic_parallelization: bool = True

    # Hallucination Prevention
    enable_fact_checking: bool = True
    fact_check_research_only: bool = True
    hallucination_threshold: int = 3

    # Chain of Thought
    enable_execution_cot: bool = True
    cot_complexity_threshold: int = 2

    # Confidence Scoring
    enable_confidence_scoring: bool = False
    min_confidence_for_delivery: float = 0.7
```

---

## Summary

This implementation strategy provides a comprehensive roadmap for optimizing the Pythinker agent system:

1. **Speed:** 40-50% latency reduction through caching, parallelization, and token optimization
2. **Accuracy:** 60-70% improvement in citation coverage through fact-checking and hallucination detection
3. **Intelligence:** 10-15% better first-pass success through CoT and structured error recovery

Implementation should proceed in priority order, with Tier 1 changes providing immediate high-impact improvements.

---

*Document compiled from codebase analysis and industry best practices.*
