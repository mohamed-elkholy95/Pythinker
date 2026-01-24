# Pythinker Agent Enhancement Plan

## Executive Summary

This comprehensive enhancement plan synthesizes architectural insights from OpenManus with deep analysis of Pythinker's existing systems. The plan identifies **42 specific enhancements** across 8 domains, prioritized by impact and implementation effort.

**Key Finding**: Pythinker already has superior implementations in several areas (token management, stuck detection, memory compaction, error classification). The primary opportunities are in **integration**, **multi-agent orchestration**, **tool coordination**, and **observability**.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Multi-Agent Orchestration](#2-multi-agent-orchestration)
3. [Tool System Enhancements](#3-tool-system-enhancements)
4. [Flow Execution Improvements](#4-flow-execution-improvements)
5. [Error Handling & Recovery](#5-error-handling--recovery)
6. [Memory & Context Management](#6-memory--context-management)
7. [Prompt Engineering](#7-prompt-engineering)
8. [MCP Integration](#8-mcp-integration)
9. [Observability & Telemetry](#9-observability--telemetry)
10. [Implementation Roadmap](#10-implementation-roadmap)

---

## 1. Architecture Overview

### Current Pythinker Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      AgentTaskRunner                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ PlanActFlow │  │DiscussFlow  │  │ WorkflowFlow (planned)  │  │
│  └──────┬──────┘  └─────────────┘  └─────────────────────────┘  │
│         │                                                        │
│  ┌──────▼──────────────────────────────────────────────────┐    │
│  │                    ExecutionAgent                        │    │
│  │  ┌────────────┐ ┌──────────────┐ ┌─────────────────┐    │    │
│  │  │TokenManager│ │StuckDetector │ │MemoryManager    │    │    │
│  │  └────────────┘ └──────────────┘ └─────────────────┘    │    │
│  │  ┌────────────┐ ┌──────────────┐ ┌─────────────────┐    │    │
│  │  │ErrorHandler│ │PromptAdapter │ │CriticAgent      │    │    │
│  │  └────────────┘ └──────────────┘ └─────────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │                        Tools                               │  │
│  │  Browser │ Shell │ File │ Search │ MCP │ Message │ Idle   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Proposed Enhanced Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      AgentTaskRunner                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              FlowOrchestrator (NEW)                      │    │
│  │  ┌────────────┐ ┌─────────────┐ ┌─────────────────────┐ │    │
│  │  │PlanActFlow │ │DiscussFlow  │ │ PlanningFlow (NEW)  │ │    │
│  │  └────────────┘ └─────────────┘ └─────────────────────┘ │    │
│  └──────────────────────────┬──────────────────────────────┘    │
│                             │                                    │
│  ┌──────────────────────────▼──────────────────────────────┐    │
│  │              AgentRegistry (NEW)                         │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐    │    │
│  │  │ExecutionAgent│ │ResearchAgent│ │ CodingAgent    │    │    │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘    │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐    │    │
│  │  │BrowserAgent │ │ DataAgent   │ │ CriticAgent    │    │    │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │            ToolCoordinator (NEW)                           │  │
│  │  ┌─────────────────┐  ┌─────────────────────────────────┐ │  │
│  │  │ ToolCollection  │  │ ToolExecutionProfiler (NEW)     │ │  │
│  │  └─────────────────┘  └─────────────────────────────────┘ │  │
│  │  ┌─────────────────┐  ┌─────────────────────────────────┐ │  │
│  │  │ ObservationLimiter│ │ ToolResultCache (NEW)          │ │  │
│  │  └─────────────────┘  └─────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Multi-Agent Orchestration

### 2.1 Agent Registry Pattern

**Current State**: Single ExecutionAgent handles all tasks.

**Enhancement**: Implement specialized agents with dynamic dispatch.

```python
# backend/app/domain/services/agents/agent_registry.py (NEW)

from enum import Enum
from typing import Dict, Optional, List
from abc import ABC, abstractmethod

class AgentType(str, Enum):
    EXECUTION = "execution"      # General task execution
    RESEARCH = "research"        # Web research and information gathering
    CODING = "coding"            # Code generation and modification
    BROWSER = "browser"          # Web automation tasks
    DATA_ANALYSIS = "data"       # Data processing and visualization
    CRITIC = "critic"            # Quality assurance and review

class AgentCapability(str, Enum):
    WEB_BROWSING = "web_browsing"
    CODE_EXECUTION = "code_execution"
    FILE_OPERATIONS = "file_operations"
    DATA_ANALYSIS = "data_analysis"
    SEARCH = "search"

class AgentRegistry:
    """Registry for specialized agents with capability-based dispatch."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._agent_types: Dict[AgentType, List[str]] = {}
        self._capabilities: Dict[str, List[AgentCapability]] = {}

    def register(
        self,
        key: str,
        agent: BaseAgent,
        agent_type: AgentType,
        capabilities: List[AgentCapability]
    ) -> None:
        """Register agent with type and capabilities."""
        self._agents[key] = agent
        self._agent_types.setdefault(agent_type, []).append(key)
        self._capabilities[key] = capabilities

    def get_agent_for_step(
        self,
        step_type: Optional[str] = None,
        required_capabilities: Optional[List[AgentCapability]] = None
    ) -> BaseAgent:
        """Select best agent for step based on type or capabilities."""
        # Priority 1: Exact type match
        if step_type:
            agent_type = AgentType(step_type.lower())
            if agent_type in self._agent_types:
                return self._agents[self._agent_types[agent_type][0]]

        # Priority 2: Capability match
        if required_capabilities:
            for key, caps in self._capabilities.items():
                if all(cap in caps for cap in required_capabilities):
                    return self._agents[key]

        # Fallback: Default execution agent
        return self._agents.get("execution")

    def get_all_agents(self) -> List[BaseAgent]:
        """Return all registered agents."""
        return list(self._agents.values())
```

### 2.2 Step-Based Agent Dispatch

**File to modify**: `backend/app/domain/services/flows/plan_act.py`

```python
# Add to PlanActFlow class

async def _execute_step_with_dispatch(
    self,
    step: Step,
    agent_registry: AgentRegistry
) -> StepResult:
    """Execute step with appropriate specialized agent."""

    # Extract agent hint from step description
    agent_type = self._extract_agent_type(step.description)

    # Get appropriate agent
    executor = agent_registry.get_agent_for_step(
        step_type=agent_type,
        required_capabilities=self._infer_capabilities(step)
    )

    # Mark step in progress
    step.status = ExecutionStatus.RUNNING
    await self._emit_step_update(step)

    try:
        result = await executor.execute(step.description)
        step.status = ExecutionStatus.COMPLETED
        return StepResult(success=True, output=result)
    except Exception as e:
        step.status = ExecutionStatus.BLOCKED
        step.notes = str(e)
        return StepResult(success=False, error=str(e))

def _extract_agent_type(self, description: str) -> Optional[str]:
    """Extract [AGENT_TYPE] prefix from step description."""
    import re
    match = re.search(r"\[([A-Z_]+)\]", description)
    if match:
        return match.group(1).lower()
    return None

def _infer_capabilities(self, step: Step) -> List[AgentCapability]:
    """Infer required capabilities from step description."""
    capabilities = []
    desc_lower = step.description.lower()

    if any(w in desc_lower for w in ["browse", "website", "page", "click"]):
        capabilities.append(AgentCapability.WEB_BROWSING)
    if any(w in desc_lower for w in ["code", "implement", "function", "class"]):
        capabilities.append(AgentCapability.CODE_EXECUTION)
    if any(w in desc_lower for w in ["file", "read", "write", "save"]):
        capabilities.append(AgentCapability.FILE_OPERATIONS)
    if any(w in desc_lower for w in ["search", "find", "lookup"]):
        capabilities.append(AgentCapability.SEARCH)

    return capabilities
```

### 2.3 Four-State Step Status Model

**Current State**: Uses `ExecutionStatus` with PENDING, RUNNING, COMPLETED.

**Enhancement**: Add BLOCKED and SKIPPED states for better error handling.

```python
# backend/app/domain/models/plan.py

class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"  # Renamed from IN_PROGRESS for clarity
    COMPLETED = "completed"
    BLOCKED = "blocked"  # NEW: Step failed and blocks dependent steps
    SKIPPED = "skipped"  # NEW: Step skipped due to condition/optimization

    @classmethod
    def get_status_marks(cls) -> Dict[str, str]:
        """Visual markers for UI display."""
        return {
            cls.PENDING.value: "[ ]",
            cls.RUNNING.value: "[→]",
            cls.COMPLETED.value: "[✓]",
            cls.BLOCKED.value: "[!]",
            cls.SKIPPED.value: "[-]",
        }

    @classmethod
    def get_active_statuses(cls) -> List[str]:
        """Statuses that indicate step needs attention."""
        return [cls.PENDING.value, cls.RUNNING.value]

    @classmethod
    def get_terminal_statuses(cls) -> List[str]:
        """Statuses that indicate step is done."""
        return [cls.COMPLETED.value, cls.BLOCKED.value, cls.SKIPPED.value]
```

### 2.4 Step Dependency Graph

**Enhancement**: Enable parallel execution of non-blocking steps.

```python
# backend/app/domain/models/plan.py

@dataclass
class Step:
    id: str
    description: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    agent_type: Optional[str] = None  # NEW: Which agent should handle this
    notes: str = ""                   # NEW: Error context or execution notes
    dependencies: List[str] = field(default_factory=list)  # NEW: Step IDs this depends on
    blocks: List[str] = field(default_factory=list)        # NEW: Step IDs blocked by this
    estimated_duration: Optional[float] = None             # NEW: For progress estimation
    actual_duration: Optional[float] = None                # NEW: For learning

class StepDependencyGraph:
    """Analyze step dependencies for parallel execution."""

    def __init__(self, steps: List[Step]):
        self._steps = {s.id: s for s in steps}
        self._graph = self._build_graph(steps)

    def get_executable_steps(self) -> List[Step]:
        """Return steps that can be executed now (no pending dependencies)."""
        executable = []
        for step in self._steps.values():
            if step.status != ExecutionStatus.PENDING:
                continue
            deps_satisfied = all(
                self._steps[dep_id].status == ExecutionStatus.COMPLETED
                for dep_id in step.dependencies
                if dep_id in self._steps
            )
            if deps_satisfied:
                executable.append(step)
        return executable

    def mark_blocked_cascade(self, blocked_step_id: str) -> List[str]:
        """Mark all steps that depend on blocked step as blocked."""
        blocked_ids = []
        to_check = [blocked_step_id]

        while to_check:
            current_id = to_check.pop(0)
            for step in self._steps.values():
                if current_id in step.dependencies and step.status == ExecutionStatus.PENDING:
                    step.status = ExecutionStatus.BLOCKED
                    step.notes = f"Blocked by step {current_id}"
                    blocked_ids.append(step.id)
                    to_check.append(step.id)

        return blocked_ids
```

---

## 3. Tool System Enhancements

### 3.1 Observation Limiting

**Current Gap**: Tool results can grow unbounded, consuming context window.

**Enhancement**: Per-tool observation limits with smart truncation.

```python
# backend/app/domain/services/tools/base.py

class BaseTool(ABC):
    """Enhanced base tool with observation limiting."""

    name: str
    description: str
    max_observe: Optional[int] = 8000  # NEW: Default observation limit

    async def execute(self, **kwargs) -> ToolResult:
        """Execute tool with observation limiting."""
        result = await self._execute_impl(**kwargs)

        if self.max_observe and result.message:
            if len(result.message) > self.max_observe:
                truncated = result.message[:self.max_observe]
                # Find last complete line/sentence
                last_newline = truncated.rfind('\n')
                if last_newline > self.max_observe * 0.8:
                    truncated = truncated[:last_newline]
                result.message = truncated + f"\n... [truncated, {len(result.message) - len(truncated)} chars omitted]"

        return result

    @abstractmethod
    async def _execute_impl(self, **kwargs) -> ToolResult:
        """Actual tool implementation."""
        pass

# Tool-specific limits (examples)
class BrowserTool(BaseTool):
    max_observe: int = 10000  # Browser content can be verbose

class ShellTool(BaseTool):
    max_observe: int = 5000   # Command output usually shorter

class SearchTool(BaseTool):
    max_observe: int = 8000   # Search results moderate size
```

### 3.2 Tool Execution Profiler

**Enhancement**: Track tool performance for optimization.

```python
# backend/app/domain/services/tools/tool_profiler.py (NEW)

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import time

@dataclass
class ToolExecutionMetrics:
    tool_name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    last_used: Optional[datetime] = None
    last_error: Optional[str] = None

    def record_execution(self, duration_ms: float, success: bool, error: Optional[str] = None):
        self.call_count += 1
        self.total_duration_ms += duration_ms
        self.avg_duration_ms = self.total_duration_ms / self.call_count
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.last_used = datetime.now()

        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
            self.last_error = error

class ToolExecutionProfiler:
    """Profile tool executions for performance monitoring."""

    def __init__(self):
        self._metrics: Dict[str, ToolExecutionMetrics] = {}

    async def profile_execution(
        self,
        tool: BaseTool,
        **kwargs
    ) -> ToolResult:
        """Execute tool with profiling."""
        if tool.name not in self._metrics:
            self._metrics[tool.name] = ToolExecutionMetrics(tool_name=tool.name)

        start_time = time.perf_counter()
        try:
            result = await tool.execute(**kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._metrics[tool.name].record_execution(
                duration_ms=duration_ms,
                success=result.success,
                error=result.error if not result.success else None
            )
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._metrics[tool.name].record_execution(
                duration_ms=duration_ms,
                success=False,
                error=str(e)
            )
            raise

    def get_slow_tools(self, threshold_ms: float = 5000) -> List[ToolExecutionMetrics]:
        """Get tools with average execution time above threshold."""
        return [m for m in self._metrics.values() if m.avg_duration_ms > threshold_ms]

    def get_unreliable_tools(self, failure_rate_threshold: float = 0.2) -> List[ToolExecutionMetrics]:
        """Get tools with failure rate above threshold."""
        return [
            m for m in self._metrics.values()
            if m.call_count > 0 and (m.failure_count / m.call_count) > failure_rate_threshold
        ]

    def get_execution_summary(self) -> Dict[str, any]:
        """Get summary of all tool executions."""
        return {
            "total_calls": sum(m.call_count for m in self._metrics.values()),
            "total_failures": sum(m.failure_count for m in self._metrics.values()),
            "slowest_tool": max(self._metrics.values(), key=lambda m: m.avg_duration_ms).tool_name if self._metrics else None,
            "most_used_tool": max(self._metrics.values(), key=lambda m: m.call_count).tool_name if self._metrics else None,
            "tools": {name: vars(m) for name, m in self._metrics.items()}
        }
```

### 3.3 Tool Result Caching

**Enhancement**: Cache deterministic tool results to avoid redundant executions.

```python
# backend/app/domain/services/tools/tool_cache.py (NEW)

import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass

@dataclass
class CachedResult:
    result: ToolResult
    cached_at: datetime
    expires_at: datetime
    cache_key: str

class ToolResultCache:
    """Cache for deterministic tool results."""

    # Tools that produce deterministic results
    CACHEABLE_TOOLS = {
        "file_read": timedelta(minutes=5),      # File content (short TTL)
        "search": timedelta(minutes=30),         # Search results (moderate TTL)
        "mcp_read_resource": timedelta(minutes=10),  # MCP resources
    }

    def __init__(self):
        self._cache: Dict[str, CachedResult] = {}

    def _compute_cache_key(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        """Compute deterministic cache key from tool call."""
        sorted_kwargs = json.dumps(kwargs, sort_keys=True)
        content = f"{tool_name}:{sorted_kwargs}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, tool_name: str, **kwargs) -> Optional[ToolResult]:
        """Get cached result if available and not expired."""
        if tool_name not in self.CACHEABLE_TOOLS:
            return None

        cache_key = self._compute_cache_key(tool_name, kwargs)
        cached = self._cache.get(cache_key)

        if cached and datetime.now() < cached.expires_at:
            return cached.result

        # Remove expired entry
        if cached:
            del self._cache[cache_key]

        return None

    def set(self, tool_name: str, result: ToolResult, **kwargs) -> None:
        """Cache a tool result."""
        if tool_name not in self.CACHEABLE_TOOLS:
            return

        ttl = self.CACHEABLE_TOOLS[tool_name]
        cache_key = self._compute_cache_key(tool_name, kwargs)
        now = datetime.now()

        self._cache[cache_key] = CachedResult(
            result=result,
            cached_at=now,
            expires_at=now + ttl,
            cache_key=cache_key
        )

    def invalidate(self, pattern: Optional[str] = None) -> int:
        """Invalidate cache entries matching pattern."""
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        to_remove = [k for k in self._cache if pattern in k]
        for key in to_remove:
            del self._cache[key]
        return len(to_remove)
```

### 3.4 Tool Coordinator

**Enhancement**: Centralized tool management with profiling and caching.

```python
# backend/app/domain/services/tools/tool_coordinator.py (NEW)

class ToolCoordinator:
    """Coordinates tool execution with profiling, caching, and observation limits."""

    def __init__(
        self,
        tools: List[BaseTool],
        enable_profiling: bool = True,
        enable_caching: bool = True
    ):
        self._tools = {tool.name: tool for tool in tools}
        self._profiler = ToolExecutionProfiler() if enable_profiling else None
        self._cache = ToolResultCache() if enable_caching else None

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute tool with full coordination."""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        # Check cache first
        if self._cache:
            cached = self._cache.get(tool_name, **kwargs)
            if cached:
                return cached

        # Execute with profiling
        if self._profiler:
            result = await self._profiler.profile_execution(tool, **kwargs)
        else:
            result = await tool.execute(**kwargs)

        # Cache result
        if self._cache and result.success:
            self._cache.set(tool_name, result, **kwargs)

        return result

    def get_tools_for_llm(self) -> List[Dict]:
        """Get tool definitions for LLM function calling."""
        return [tool.to_function_definition() for tool in self._tools.values()]

    def add_tool(self, tool: BaseTool) -> None:
        """Dynamically add a tool."""
        self._tools[tool.name] = tool

    def remove_tool(self, tool_name: str) -> None:
        """Dynamically remove a tool."""
        self._tools.pop(tool_name, None)
```

---

## 4. Flow Execution Improvements

### 4.1 PlanningFlow Pattern

**Enhancement**: Implement hierarchical planning with LLM-generated plans.

```python
# backend/app/domain/services/flows/planning_flow.py (NEW)

from typing import Dict, List, Optional, Tuple
import re

class PlanningFlow:
    """Hierarchical planning flow with step-based execution."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        llm: LLM,
        planning_tool: PlanningTool
    ):
        self._registry = agent_registry
        self._llm = llm
        self._planning_tool = planning_tool
        self._active_plan_id: Optional[str] = None
        self._current_step_index: Optional[int] = None

    async def execute(self, input_text: str) -> str:
        """Execute planning flow with agent dispatch."""
        # Phase 1: Create initial plan
        await self._create_initial_plan(input_text)

        # Phase 2: Execute steps
        results = []
        while True:
            step_index, step_info = await self._get_current_step_info()

            if step_index is None:
                # All steps complete
                break

            # Get appropriate executor
            step_type = step_info.get("type")
            executor = self._registry.get_agent_for_step(step_type)

            # Execute step
            step_result = await self._execute_step(executor, step_info)
            results.append(step_result)

            # Check for early termination
            if executor.state == AgentState.FINISHED:
                break

        # Phase 3: Finalize
        return await self._finalize_plan(results)

    async def _create_initial_plan(self, request: str) -> None:
        """Use LLM to create structured plan."""
        # Get agent descriptions for planning
        agents_info = [
            {"name": key.upper(), "description": agent.description}
            for key, agent in self._registry._agents.items()
        ]

        system_prompt = f"""You are a planning assistant. Create a step-by-step plan.

Available agents: {json.dumps(agents_info)}

When creating steps, prefix with agent name: '[AGENT_NAME] step description'
Example: '[RESEARCH] Find documentation on the topic'

Create 3-7 clear, actionable steps."""

        response = await self._llm.ask(
            messages=[{"role": "user", "content": f"Create a plan for: {request}"}],
            system_prompt=system_prompt
        )

        # Parse steps from response
        steps = self._parse_steps(response.content)

        # Create plan via tool
        plan_id = f"plan_{int(time.time())}"
        await self._planning_tool.execute(
            command="create",
            plan_id=plan_id,
            title=request[:50],
            steps=steps
        )

        self._active_plan_id = plan_id

    async def _get_current_step_info(self) -> Tuple[Optional[int], Optional[Dict]]:
        """Get next pending step."""
        plan_data = self._planning_tool.plans[self._active_plan_id]
        steps = plan_data.get("steps", [])
        statuses = plan_data.get("step_statuses", [])

        for i, step in enumerate(steps):
            status = statuses[i] if i < len(statuses) else "not_started"
            if status in ["not_started", "in_progress"]:
                # Extract agent type
                step_info = {"text": step, "index": i}
                type_match = re.search(r"\[([A-Z_]+)\]", step)
                if type_match:
                    step_info["type"] = type_match.group(1).lower()

                # Mark as in progress
                await self._planning_tool.execute(
                    command="mark_step",
                    plan_id=self._active_plan_id,
                    step_index=i,
                    step_status="in_progress"
                )

                return i, step_info

        return None, None

    async def _execute_step(self, executor: BaseAgent, step_info: Dict) -> str:
        """Execute single step with agent."""
        step_prompt = f"Execute this step: {step_info['text']}"
        result = await executor.run(step_prompt)

        # Mark completed
        await self._planning_tool.execute(
            command="mark_step",
            plan_id=self._active_plan_id,
            step_index=step_info["index"],
            step_status="completed"
        )

        return result

    async def _finalize_plan(self, results: List[str]) -> str:
        """Summarize completed plan."""
        plan_text = await self._planning_tool.execute(
            command="get",
            plan_id=self._active_plan_id
        )

        summary_prompt = f"""Summarize the completed plan:

{plan_text}

Results from each step:
{chr(10).join(f'Step {i+1}: {r[:500]}' for i, r in enumerate(results))}

Provide a concise summary of what was accomplished."""

        response = await self._llm.ask(
            messages=[{"role": "user", "content": summary_prompt}]
        )

        return f"Plan completed:\n\n{response.content}"
```

### 4.2 Async State Context Manager

**Enhancement**: Safe state transitions with automatic rollback.

```python
# backend/app/domain/services/agents/base.py

from contextlib import asynccontextmanager

class BaseAgent:

    @asynccontextmanager
    async def state_context(self, new_state: AgentState):
        """Context manager for atomic state transitions."""
        previous_state = self.state
        self.state = new_state
        try:
            yield
        except Exception as e:
            self.state = AgentState.ERROR
            logger.error(f"State transition failed: {previous_state} -> {new_state}: {e}")
            raise
        finally:
            # Optionally restore previous state (depends on use case)
            pass

    async def run_step(self) -> StepResult:
        """Execute single step with state management."""
        async with self.state_context(AgentState.RUNNING):
            try:
                should_act = await self.think()
                if not should_act:
                    return StepResult(action_taken=False)
                return await self.act()
            except Exception as e:
                return StepResult(action_taken=True, error=str(e))
```

### 4.3 Plan Finalization with Two-Tier Summarization

**Enhancement**: LLM-based summarization with fallback.

```python
# backend/app/domain/services/flows/plan_act.py

async def _finalize_plan(self) -> str:
    """Finalize with two-tier summarization."""
    plan_text = self._format_plan_text()

    # Tier 1: Fast LLM-only summarization
    try:
        response = await self._llm.ask(
            messages=[{
                "role": "user",
                "content": f"Summarize this execution concisely:\n\n{plan_text}"
            }],
            max_tokens=500
        )
        return response.content
    except Exception as e:
        logger.warning(f"LLM summarization failed: {e}")

    # Tier 2: Agent-based summary
    try:
        return await self._executor.summarize(plan_text)
    except Exception as e:
        logger.warning(f"Agent summarization failed: {e}")

    # Tier 3: Graceful degradation
    completed = sum(1 for s in self._plan.steps if s.status == ExecutionStatus.COMPLETED)
    return f"Plan completed: {completed}/{len(self._plan.steps)} steps executed successfully."
```

---

## 5. Error Handling & Recovery

### 5.1 Exponential Backoff Integration

**Current Gap**: ErrorHandler lacks exponential backoff.

**Enhancement**: Add backoff to ErrorContext and recovery strategies.

```python
# backend/app/domain/services/agents/error_handler.py

import asyncio
import random

@dataclass
class ErrorContext:
    error_type: ErrorType
    error_message: str
    timestamp: datetime
    recoverable: bool
    recovery_strategy: str
    tool_name: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    # NEW: Backoff configuration
    backoff_factor: float = 1.5
    min_retry_delay: float = 0.3
    max_retry_delay: float = 30.0
    jitter: bool = True

    def get_retry_delay(self) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        delay = self.min_retry_delay * (self.backoff_factor ** self.retry_count)
        delay = min(delay, self.max_retry_delay)

        if self.jitter:
            # Add random jitter ±25%
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0.1, delay)

class ErrorHandler:

    async def handle_with_retry(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> Tuple[bool, Any]:
        """Execute operation with automatic retry and backoff."""
        last_error = None
        error_context = None

        for attempt in range(4):  # 1 initial + 3 retries
            try:
                result = await operation(*args, **kwargs)

                # Record recovery success if this was a retry
                if attempt > 0 and error_context:
                    self._record_recovery_success(error_context)

                return True, result

            except Exception as e:
                error_context = self.classify_error(e)
                error_context.retry_count = attempt

                if not error_context.recoverable or attempt >= error_context.max_retries:
                    self._record_recovery_failure(error_context)
                    return False, error_context

                delay = error_context.get_retry_delay()
                logger.info(f"Retry {attempt + 1}/{error_context.max_retries} after {delay:.2f}s")
                await asyncio.sleep(delay)

                last_error = e

        return False, error_context

    def _record_recovery_success(self, context: ErrorContext) -> None:
        """Track successful recovery for pattern analysis."""
        self._recovery_stats.setdefault(context.error_type, {"success": 0, "failure": 0})
        self._recovery_stats[context.error_type]["success"] += 1

    def _record_recovery_failure(self, context: ErrorContext) -> None:
        """Track failed recovery for pattern analysis."""
        self._recovery_stats.setdefault(context.error_type, {"success": 0, "failure": 0})
        self._recovery_stats[context.error_type]["failure"] += 1
```

### 5.2 Enhanced Stuck Detection

**Enhancement**: Add functional stuck detection and context-aware recovery.

```python
# backend/app/domain/services/agents/stuck_detector.py

class StuckDetector:

    def __init__(self, ...):
        # ... existing init ...
        self._attempted_strategies: Set[str] = set()
        self._tool_result_patterns: Dict[str, List[str]] = {}  # tool -> recent result categories

    def detect_functional_stuck(self) -> bool:
        """Detect when different queries produce same result category.

        Example: Agent searches with different terms but keeps getting "no results".
        """
        for tool_name, results in self._tool_result_patterns.items():
            if len(results) < 3:
                continue

            # Check if last N results are functionally equivalent
            recent = results[-5:]
            categories = set(self._categorize_result(r) for r in recent)

            if len(categories) == 1:  # All same category
                logger.warning(f"Functional stuck: {tool_name} returning same category {recent[-1]}")
                return True

        return False

    def _categorize_result(self, result: str) -> str:
        """Categorize result into functional categories."""
        result_lower = result.lower()

        if any(w in result_lower for w in ["not found", "no results", "empty", "none"]):
            return "no_results"
        if any(w in result_lower for w in ["error", "failed", "exception"]):
            return "error"
        if any(w in result_lower for w in ["success", "completed", "done"]):
            return "success"
        if len(result) < 50:
            return "minimal_output"

        return "normal"

    def get_context_aware_recovery_prompt(self, recent_tools: List[str]) -> str:
        """Generate recovery prompt that references specific tools being overused."""
        if not recent_tools:
            return self._recovery_prompts[min(self._recovery_attempts, 2)]

        # Count tool usage
        tool_counts = {}
        for tool in recent_tools[-10:]:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1

        most_used = max(tool_counts, key=tool_counts.get)
        count = tool_counts[most_used]

        if count >= 5:
            return f"""You've called '{most_used}' {count} times recently with similar patterns.

Consider:
1. Using a completely different tool for this subtask
2. Breaking the problem into smaller parts
3. Verifying your assumptions about what this tool can do
4. Checking if the target resource/element has changed"""

        return self._recovery_prompts[min(self._recovery_attempts, 2)]

    def record_recovery_strategy_used(self, strategy: str) -> None:
        """Track which strategies have been attempted."""
        self._attempted_strategies.add(strategy)

    def get_untried_strategies(self) -> List[str]:
        """Return strategies not yet attempted."""
        all_strategies = {
            "use_different_tool",
            "break_into_subtasks",
            "verify_assumptions",
            "try_alternative_approach",
            "ask_for_clarification"
        }
        return list(all_strategies - self._attempted_strategies)
```

### 5.3 Integration Bridge

**Enhancement**: Connect error handling components that currently operate independently.

```python
# backend/app/domain/services/agents/error_integration.py (NEW)

class ErrorIntegrationBridge:
    """Bridges ErrorHandler, StuckDetector, and PatternAnalyzer."""

    def __init__(
        self,
        error_handler: ErrorHandler,
        stuck_detector: StuckDetector,
        pattern_analyzer: ErrorPatternAnalyzer,
        token_manager: TokenManager,
        memory_manager: MemoryManager
    ):
        self._error_handler = error_handler
        self._stuck_detector = stuck_detector
        self._pattern_analyzer = pattern_analyzer
        self._token_manager = token_manager
        self._memory_manager = memory_manager

    async def assess_agent_health(self) -> AgentHealthStatus:
        """Comprehensive health assessment across all systems."""
        return AgentHealthStatus(
            error_state=self._error_handler.get_current_state(),
            stuck_state=self._stuck_detector.is_stuck(),
            stuck_type=self._stuck_detector.get_stuck_type(),
            token_pressure=self._token_manager.get_context_pressure(),
            patterns_detected=self._pattern_analyzer.analyze_patterns(
                self._error_handler.get_recent_errors()
            ),
            recommended_actions=self._get_recommended_actions()
        )

    async def handle_iteration_end(self, response: Dict) -> IterationGuidance:
        """Process end of iteration across all systems."""
        # Track in stuck detector
        is_stuck = self._stuck_detector.track_response(response)

        # Check for error patterns
        recent_errors = self._error_handler.get_recent_errors(limit=10)
        patterns = self._pattern_analyzer.analyze_patterns(recent_errors)

        # Check token pressure
        pressure = self._token_manager.get_context_pressure()

        # Determine if compaction needed
        should_compact = (
            pressure.level in [PressureLevel.CRITICAL, PressureLevel.OVERFLOW] or
            (is_stuck and self._stuck_detector.recovery_attempts > 2)
        )

        if should_compact:
            await self._memory_manager.trigger_compaction()

        return IterationGuidance(
            should_continue=not is_stuck or self._stuck_detector.recovery_attempts < 5,
            inject_prompt=self._get_guidance_prompt(is_stuck, patterns, pressure),
            trigger_compaction=should_compact,
            patterns=patterns
        )

    def _get_guidance_prompt(
        self,
        is_stuck: bool,
        patterns: List[DetectedPattern],
        pressure: PressureStatus
    ) -> Optional[str]:
        """Generate unified guidance prompt."""
        prompts = []

        if is_stuck:
            prompts.append(self._stuck_detector.get_recovery_prompt())

        if patterns:
            top_pattern = max(patterns, key=lambda p: p.confidence)
            if top_pattern.confidence > 0.7:
                prompts.append(f"Pattern detected: {top_pattern.suggestion}")

        if pressure.level != PressureLevel.NORMAL:
            prompts.append(pressure.to_context_signal())

        return "\n\n".join(prompts) if prompts else None
```

---

## 6. Memory & Context Management

### 6.1 Proactive Compaction Triggers

**Current Gap**: Compaction only triggered reactively on overflow.

**Enhancement**: Proactive compaction based on multiple signals.

```python
# backend/app/domain/services/agents/memory_manager.py

class MemoryManager:

    def should_trigger_compaction(
        self,
        pressure: PressureStatus,
        recent_tools: List[str],
        iteration_count: int
    ) -> Tuple[bool, str]:
        """Determine if compaction should be triggered with reason."""

        # Rule 1: Critical pressure
        if pressure.level in [PressureLevel.CRITICAL, PressureLevel.OVERFLOW]:
            return True, f"Token pressure at {pressure.level.value}"

        # Rule 2: Verbose tool output
        verbose_tools = {"browser_view", "shell_execute", "file_read"}
        recent_verbose = sum(1 for t in recent_tools[-5:] if t in verbose_tools)
        if recent_verbose >= 3 and pressure.level == PressureLevel.WARNING:
            return True, "Multiple verbose tool outputs detected"

        # Rule 3: Periodic compaction (every 20 iterations)
        if iteration_count > 0 and iteration_count % 20 == 0:
            if pressure.level != PressureLevel.NORMAL:
                return True, f"Periodic compaction at iteration {iteration_count}"

        # Rule 4: Memory growth rate
        if hasattr(self, '_token_history') and len(self._token_history) >= 5:
            growth_rate = (self._token_history[-1] - self._token_history[-5]) / 5
            if growth_rate > 1000:  # >1000 tokens per iteration
                return True, f"High memory growth rate: {growth_rate:.0f} tokens/iteration"

        return False, ""
```

### 6.2 LLM-Based Extraction for Unknown Tools

**Enhancement**: Use LLM to summarize unknown tool outputs.

```python
# backend/app/domain/services/agents/memory_manager.py

class MemoryManager:

    async def extract_with_llm(
        self,
        function_name: str,
        content: str,
        llm: LLM
    ) -> ExtractionResult:
        """Use LLM to extract key information from unknown tool output."""

        # Only for tools we don't have extractors for
        if function_name in self.SUMMARIZABLE_FUNCTIONS:
            return self._extract_known(function_name, content)

        prompt = f"""Extract key information from this tool output.

Tool: {function_name}
Output:
{content[:4000]}  # Limit input

Provide a concise summary (max 200 words) that preserves:
1. Success/failure status
2. Key data or results
3. Any URLs, paths, or identifiers
4. Error messages if present

Summary:"""

        try:
            response = await llm.ask(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )

            return ExtractionResult(
                key_facts=response.content,
                success_indicator=self._infer_success(content),
                extraction_method="llm",
                confidence=0.8
            )
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return self._fallback_extraction(content)

    def _fallback_extraction(self, content: str) -> ExtractionResult:
        """Fallback extraction using heuristics."""
        # Take first 500 and last 200 chars
        if len(content) > 700:
            summary = content[:500] + "\n...\n" + content[-200:]
        else:
            summary = content

        return ExtractionResult(
            key_facts=summary,
            success_indicator=self._infer_success(content),
            extraction_method="heuristic",
            confidence=0.5
        )
```

### 6.3 Archive Integration

**Enhancement**: Actually persist compacted content to storage.

```python
# backend/app/domain/services/agents/memory_manager.py

class MemoryManager:

    def __init__(self, ..., file_storage: FileStorage):
        self._file_storage = file_storage
        self._archive_index: Dict[str, str] = {}  # message_id -> archive_path

    async def compact_and_archive(
        self,
        message: Dict[str, Any],
        session_id: str
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Compact message and archive full content."""

        # Extract content for compaction
        content = message.get("content", "")
        function_name = self._get_function_name(message)

        if not content or len(content) < 500:
            return message, None  # Don't compact small messages

        # Extract key information
        extraction = await self._extract(function_name, content)

        # Archive full content
        message_id = message.get("id", str(uuid.uuid4()))
        archive_path = f"/archives/{session_id}/{message_id}.txt"

        try:
            await self._file_storage.write(
                archive_path,
                json.dumps({
                    "original_content": content,
                    "function_name": function_name,
                    "archived_at": datetime.now().isoformat(),
                    "extraction_method": extraction.extraction_method
                })
            )
            self._archive_index[message_id] = archive_path
        except Exception as e:
            logger.warning(f"Failed to archive message: {e}")
            archive_path = None

        # Create compacted message
        compacted = {
            **message,
            "content": extraction.key_facts,
            "_compacted": True,
            "_archive_path": archive_path
        }

        return compacted, archive_path

    async def retrieve_archived(self, message_id: str) -> Optional[str]:
        """Retrieve original content from archive."""
        archive_path = self._archive_index.get(message_id)
        if not archive_path:
            return None

        try:
            archived = await self._file_storage.read(archive_path)
            data = json.loads(archived)
            return data.get("original_content")
        except Exception as e:
            logger.error(f"Failed to retrieve archive: {e}")
            return None
```

---

## 7. Prompt Engineering

### 7.1 Dynamic Section Pruning

**Current Gap**: All prompt sections included regardless of available tools.

**Enhancement**: Only include relevant prompt sections.

```python
# backend/app/domain/services/prompts/system.py

def build_system_prompt(
    available_tools: List[str],
    task_context: Optional[str] = None
) -> str:
    """Build system prompt with only relevant sections."""

    sections = [CORE_PROMPT]

    # Map tools to prompt sections
    tool_section_map = {
        "browser_navigate": BROWSER_RULES,
        "browser_click": BROWSER_RULES,
        "browser_view": BROWSER_RULES,
        "shell_execute": SHELL_RULES,
        "file_read": FILE_RULES,
        "file_write": FILE_RULES,
        "search": RESEARCH_RULES,
        "mcp_": DATASOURCE_RULES,  # Prefix match for MCP tools
    }

    included_sections = set()
    for tool in available_tools:
        for tool_prefix, section in tool_section_map.items():
            if tool.startswith(tool_prefix) or tool == tool_prefix:
                included_sections.add(section)

    sections.extend(included_sections)

    # Add task-specific context if provided
    if task_context:
        sections.append(f"\n---\nTask Context:\n{task_context}\n---\n")

    return "\n\n".join(sections)
```

### 7.2 Multi-Tier Context Awareness

**Enhancement**: Track context stack instead of single context.

```python
# backend/app/domain/services/agents/prompt_adapter.py

@dataclass
class ExecutionContext:
    primary_context: ContextType
    context_stack: List[ContextType] = field(default_factory=list)
    context_durations: Dict[ContextType, int] = field(default_factory=dict)

    def push_context(self, context: ContextType) -> None:
        """Push new context onto stack."""
        if self.context_stack and self.context_stack[-1] == context:
            self.context_durations[context] = self.context_durations.get(context, 0) + 1
        else:
            self.context_stack.append(context)
            self.context_durations[context] = 1

    def get_dominant_context(self) -> ContextType:
        """Get context with longest duration in stack."""
        if not self.context_durations:
            return self.primary_context
        return max(self.context_durations, key=self.context_durations.get)

    def is_context_stuck(self, threshold: int = 10) -> bool:
        """Check if stuck in same context too long."""
        dominant = self.get_dominant_context()
        return self.context_durations.get(dominant, 0) >= threshold

class PromptAdapter:

    def get_focused_guidance(self, context: ExecutionContext) -> Optional[str]:
        """Generate guidance focused on current execution state."""

        # Check for context stuckness
        if context.is_context_stuck():
            dominant = context.get_dominant_context()
            return f"""You've been working in {dominant.value} context for {context.context_durations[dominant]} iterations.

Consider:
1. Is this approach making progress?
2. Would a different tool/approach be more effective?
3. Can you complete this subtask and move on?"""

        # Normal context guidance
        guidance = CONTEXT_GUIDANCE.get(context.primary_context)
        if guidance and context.iteration_count % 5 == 0:
            return guidance

        return None
```

---

## 8. MCP Integration

### 8.1 Runtime Tool Discovery

**Enhancement**: Periodic refresh of MCP tools with change detection.

```python
# backend/app/domain/services/tools/mcp.py

class MCPClientManager:

    async def refresh_tools(self) -> Tuple[List[str], List[str], List[str]]:
        """Refresh tools and detect changes.

        Returns: (added_tools, removed_tools, changed_tools)
        """
        current_schemas = {}

        for server_id, session in self._sessions.items():
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    tool_name = f"mcp_{server_id}_{tool.name}"
                    current_schemas[tool_name] = {
                        "name": tool.name,
                        "description": tool.description,
                        "schema": tool.inputSchema
                    }
            except Exception as e:
                logger.warning(f"Failed to refresh tools from {server_id}: {e}")

        # Detect changes
        current_names = set(current_schemas.keys())
        previous_names = set(self._tool_schemas.keys())

        added = list(current_names - previous_names)
        removed = list(previous_names - current_names)

        # Detect schema changes
        changed = []
        for name in current_names.intersection(previous_names):
            if current_schemas[name] != self._tool_schemas.get(name):
                changed.append(name)

        # Update stored schemas
        self._tool_schemas = current_schemas

        # Log changes
        if added:
            logger.info(f"MCP tools added: {added}")
        if removed:
            logger.info(f"MCP tools removed: {removed}")
        if changed:
            logger.info(f"MCP tools changed: {changed}")

        return added, removed, changed

    async def periodic_refresh(self, interval_steps: int = 5) -> None:
        """Call this every N steps to refresh tools."""
        if self._step_count % interval_steps == 0:
            added, removed, changed = await self.refresh_tools()

            # Notify agent of changes
            if added or removed or changed:
                await self._emit_tool_change_event(added, removed, changed)
```

### 8.2 Resource Prefetching

**Enhancement**: Eagerly load frequently-used resources.

```python
# backend/app/domain/services/tools/mcp.py

class MCPClientManager:

    async def prefetch_resources(
        self,
        patterns: List[str],
        max_resources: int = 10
    ) -> Dict[str, Any]:
        """Eagerly load resources matching patterns."""
        prefetched = {}

        all_resources = await self.list_all_resources()
        matching = [
            r for r in all_resources
            if any(p in r.uri for p in patterns)
        ][:max_resources]

        for resource in matching:
            try:
                content = await self.read_resource(resource.uri)
                prefetched[resource.uri] = content
                logger.debug(f"Prefetched resource: {resource.uri}")
            except Exception as e:
                logger.warning(f"Failed to prefetch {resource.uri}: {e}")

        return prefetched
```

---

## 9. Observability & Telemetry

### 9.1 Error Handling Metrics

**Enhancement**: Track recovery effectiveness.

```python
# backend/app/infrastructure/observability/metrics.py (NEW)

from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime

@dataclass
class ErrorHandlingMetrics:
    # Recovery tracking
    recovery_attempts: int = 0
    recovery_successes: int = 0
    recovery_failures: int = 0

    # By error type
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    recoveries_by_type: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Stuck detection
    stuck_detections: int = 0
    stuck_escapes: int = 0
    false_positive_stucks: int = 0

    # Pattern detection
    patterns_detected: int = 0
    patterns_acted_on: int = 0

    @property
    def recovery_success_rate(self) -> float:
        if self.recovery_attempts == 0:
            return 0.0
        return self.recovery_successes / self.recovery_attempts

    @property
    def stuck_escape_rate(self) -> float:
        if self.stuck_detections == 0:
            return 0.0
        return self.stuck_escapes / self.stuck_detections

    def record_error(self, error_type: str) -> None:
        self.errors_by_type[error_type] = self.errors_by_type.get(error_type, 0) + 1

    def record_recovery_attempt(self, error_type: str, success: bool) -> None:
        self.recovery_attempts += 1
        if success:
            self.recovery_successes += 1
        else:
            self.recovery_failures += 1

        self.recoveries_by_type.setdefault(error_type, {"success": 0, "failure": 0})
        self.recoveries_by_type[error_type]["success" if success else "failure"] += 1

    def to_dict(self) -> Dict:
        return {
            "recovery_success_rate": self.recovery_success_rate,
            "stuck_escape_rate": self.stuck_escape_rate,
            "total_errors": sum(self.errors_by_type.values()),
            "recovery_attempts": self.recovery_attempts,
            "patterns_detected": self.patterns_detected,
            "errors_by_type": self.errors_by_type,
            "recoveries_by_type": self.recoveries_by_type
        }
```

### 9.2 Decision Logging

**Enhancement**: Log detailed reasoning for debugging.

```python
# backend/app/infrastructure/observability/decision_logger.py (NEW)

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import datetime

@dataclass
class Decision:
    timestamp: datetime
    component: str  # e.g., "stuck_detector", "error_handler"
    decision_type: str  # e.g., "stuck_detected", "recovery_triggered"
    inputs: Dict[str, Any]
    output: Any
    reasoning: str

class DecisionLogger:
    """Log detailed decision reasoning for observability."""

    def __init__(self):
        self._decisions: List[Decision] = []
        self._logger = logging.getLogger("decisions")

    def log_decision(
        self,
        component: str,
        decision_type: str,
        inputs: Dict[str, Any],
        output: Any,
        reasoning: str
    ) -> None:
        """Log a decision with full context."""
        decision = Decision(
            timestamp=datetime.now(),
            component=component,
            decision_type=decision_type,
            inputs=inputs,
            output=output,
            reasoning=reasoning
        )

        self._decisions.append(decision)

        # Also log to standard logging
        self._logger.info(
            f"[{component}] {decision_type}: {reasoning}",
            extra={
                "inputs": inputs,
                "output": output
            }
        )

    def get_recent_decisions(self, limit: int = 20) -> List[Decision]:
        return self._decisions[-limit:]

    def get_decisions_by_component(self, component: str) -> List[Decision]:
        return [d for d in self._decisions if d.component == component]

# Usage example in StuckDetector:
class StuckDetector:
    def __init__(self, ..., decision_logger: DecisionLogger):
        self._decision_logger = decision_logger

    def track_response(self, response: Dict) -> bool:
        # ... detection logic ...

        self._decision_logger.log_decision(
            component="stuck_detector",
            decision_type="stuck_check",
            inputs={
                "response_hash": content_hash,
                "window_size": self._window_size,
                "recent_hashes": list(self._response_hashes[-5:])
            },
            output=is_stuck,
            reasoning=f"{'Stuck' if is_stuck else 'Not stuck'}: "
                     f"{duplicate_count} identical in last {self._window_size}, "
                     f"semantic_similarity={semantic_sim:.2f}"
        )

        return is_stuck
```

---

## 10. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)

**Priority: Critical**

| Task | Files | Effort | Impact |
|------|-------|--------|--------|
| Add observation limiting to tools | `tools/base.py`, all tool files | Medium | High |
| Implement exponential backoff in ErrorHandler | `agents/error_handler.py` | Low | High |
| Add BLOCKED/SKIPPED step statuses | `models/plan.py` | Low | Medium |
| Create ErrorIntegrationBridge | `agents/error_integration.py` (new) | Medium | High |
| Add tool execution profiler | `tools/tool_profiler.py` (new) | Medium | Medium |

### Phase 2: Multi-Agent (Weeks 3-4)

**Priority: High**

| Task | Files | Effort | Impact |
|------|-------|--------|--------|
| Implement AgentRegistry | `agents/agent_registry.py` (new) | Medium | High |
| Create specialized agents (Research, Coding, Browser) | `agents/*.py` (new) | High | High |
| Add step-based agent dispatch | `flows/plan_act.py` | Medium | High |
| Implement PlanningFlow | `flows/planning_flow.py` (new) | High | High |

### Phase 3: Context Management (Weeks 5-6)

**Priority: High**

| Task | Files | Effort | Impact |
|------|-------|--------|--------|
| Proactive compaction triggers | `agents/memory_manager.py` | Medium | High |
| LLM-based extraction for unknown tools | `agents/memory_manager.py` | Medium | Medium |
| Archive integration | `agents/memory_manager.py` | Medium | Medium |
| Dynamic prompt section pruning | `prompts/system.py` | Low | Medium |

### Phase 4: MCP & Tools (Weeks 7-8)

**Priority: Medium**

| Task | Files | Effort | Impact |
|------|-------|--------|--------|
| Runtime MCP tool discovery | `tools/mcp.py` | Medium | Medium |
| Tool result caching | `tools/tool_cache.py` (new) | Medium | Medium |
| ToolCoordinator | `tools/tool_coordinator.py` (new) | Medium | Medium |
| Resource prefetching | `tools/mcp.py` | Low | Low |

### Phase 5: Observability (Weeks 9-10)

**Priority: Medium**

| Task | Files | Effort | Impact |
|------|-------|--------|--------|
| Error handling metrics | `observability/metrics.py` (new) | Medium | Medium |
| Decision logging | `observability/decision_logger.py` (new) | Medium | Medium |
| Dashboard integration | Frontend updates | High | Medium |
| Performance reporting | `tools/tool_profiler.py` | Low | Low |

---

## Summary

### Enhancements by Category

| Category | Count | High Priority |
|----------|-------|---------------|
| Multi-Agent Orchestration | 8 | 5 |
| Tool System | 7 | 3 |
| Flow Execution | 5 | 3 |
| Error Handling | 6 | 4 |
| Memory & Context | 5 | 3 |
| Prompt Engineering | 4 | 2 |
| MCP Integration | 4 | 2 |
| Observability | 3 | 1 |
| **Total** | **42** | **23** |

### Key Architectural Principles

1. **Modular Integration**: Components work together via bridges, not direct coupling
2. **Graceful Degradation**: Every enhancement has fallback behavior
3. **Observable by Default**: All decisions logged with reasoning
4. **Performance Aware**: Profiling and caching built into core paths
5. **Backward Compatible**: Existing functionality preserved

### Expected Outcomes

- **30-50% reduction** in token usage through smarter context management
- **Improved reliability** via integrated error handling and recovery
- **Faster task completion** through parallel step execution
- **Better debugging** with decision logging and metrics
- **Scalable architecture** supporting specialized agents

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Author: Claude Code Analysis*
