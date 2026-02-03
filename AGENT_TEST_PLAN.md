# Pythinker Agent Testing Plan

## Overview

This comprehensive test plan follows 2026 best practices for AI agent evaluation, combining unit testing, integration testing, end-to-end testing, and systematic evaluation metrics.

---

## Table of Contents

1. [Testing Philosophy](#1-testing-philosophy)
2. [Test Architecture](#2-test-architecture)
3. [Phase 1: Unit Tests - Agent Components](#phase-1-unit-tests---agent-components)
4. [Phase 2: Integration Tests - Workflow Pipelines](#phase-2-integration-tests---workflow-pipelines)
5. [Phase 3: End-to-End Tests - Complete Flows](#phase-3-end-to-end-tests---complete-flows)
6. [Phase 4: Evaluation Framework - LLM Quality](#phase-4-evaluation-framework---llm-quality)
7. [Phase 5: Regression & CI/CD Integration](#phase-5-regression--cicd-integration)
8. [Implementation Schedule](#implementation-schedule)

---

## 1. Testing Philosophy

### Core Principles (2026 Best Practices)

1. **Grade What Agents Produce, Not the Path** - Avoid brittle tests that check specific tool call sequences
2. **Deterministic Where Possible** - Use mocked LLMs for unit/integration tests
3. **LLM Graders for Subjective Outputs** - Use LLM-as-judge for quality assessment
4. **Component-Level Testing** - Test each agent component in isolation first
5. **Traceability** - Link every test result to specific prompt/model/dataset versions
6. **Continuous Eval Loop** - Regression suites run on every change

### Test Pyramid

```
                    ┌─────────────────┐
                    │   E2E Tests     │  ← Real LLM, Full workflow
                    │   (10 tests)    │
                ┌───┴─────────────────┴───┐
                │   Integration Tests     │  ← Mocked LLM, Multi-component
                │       (30 tests)        │
            ┌───┴─────────────────────────┴───┐
            │         Unit Tests              │  ← Isolated components
            │          (100+ tests)           │
        ┌───┴─────────────────────────────────┴───┐
        │           Evaluation Framework          │  ← Metrics & benchmarks
        │              (50+ cases)                │
        └─────────────────────────────────────────┘
```

---

## 2. Test Architecture

### Directory Structure

```
backend/tests/
├── conftest.py                    # Shared fixtures (existing)
├── unit/                          # NEW: Unit tests
│   ├── agents/
│   │   ├── test_planner.py
│   │   ├── test_execution.py
│   │   ├── test_reflection.py
│   │   ├── test_verifier.py
│   │   ├── test_stuck_detector.py
│   │   ├── test_complexity_assessor.py
│   │   ├── test_security_assessor.py
│   │   └── test_hallucination_detector.py
│   ├── flows/
│   │   ├── test_fast_path.py
│   │   ├── test_checkpoint_manager.py
│   │   └── test_parallel_executor.py
│   └── tools/
│       ├── test_tool_selection.py
│       ├── test_tool_execution.py
│       └── test_tool_error_handling.py
├── integration/                   # NEW: Integration tests
│   ├── test_plan_execute_flow.py
│   ├── test_langgraph_workflow.py
│   ├── test_multi_agent_handoff.py
│   ├── test_error_recovery.py
│   └── test_memory_integration.py
├── e2e/                          # NEW: End-to-end tests
│   ├── test_simple_tasks.py
│   ├── test_complex_research.py
│   ├── test_tool_heavy_tasks.py
│   └── test_error_scenarios.py
└── evals/                        # ENHANCED: Evaluation framework
    ├── datasets/
    │   ├── planning_cases.json
    │   ├── execution_cases.json
    │   ├── research_cases.json
    │   └── error_cases.json
    ├── graders/
    │   ├── deterministic.py
    │   ├── llm_judge.py
    │   └── composite.py
    └── benchmarks/
        ├── latency_benchmark.py
        ├── accuracy_benchmark.py
        └── cost_benchmark.py
```

### Fixture Enhancement Plan

```python
# conftest.py additions

# === LLM Response Factories ===
@pytest.fixture
def mock_llm_plan_response():
    """Factory for planning responses."""
    def _create(steps: list[dict], complexity: str = "medium"):
        return {
            "plan": {
                "steps": steps,
                "complexity": complexity,
                "estimated_iterations": len(steps)
            }
        }
    return _create

@pytest.fixture
def mock_llm_execution_response():
    """Factory for execution responses."""
    def _create(tool_calls: list[dict] = None, final_answer: str = None):
        return {
            "tool_calls": tool_calls or [],
            "final_answer": final_answer,
            "reasoning": "Test reasoning"
        }
    return _create

@pytest.fixture
def mock_llm_reflection_response():
    """Factory for reflection responses."""
    def _create(decision: str = "continue", feedback: str = ""):
        return {
            "decision": decision,  # continue, adjust, replan, escalate
            "feedback": feedback,
            "confidence": 0.85
        }
    return _create

# === LangGraph State Fixtures ===
@pytest.fixture
def initial_plan_act_state():
    """Base state for LangGraph workflow tests."""
    return {
        "user_message": "test message",
        "plan": None,
        "current_step": 0,
        "iteration_count": 0,
        "verification_loops": 0,
        "error_count": 0,
        "pending_events": [],
        "recent_tools": [],
        "plan_created": False,
        "all_steps_done": False
    }

@pytest.fixture
def state_with_plan(initial_plan_act_state, mock_llm_plan_response):
    """State with an existing plan."""
    state = initial_plan_act_state.copy()
    state["plan"] = mock_llm_plan_response([
        {"step": 1, "action": "search", "description": "Search for info"},
        {"step": 2, "action": "analyze", "description": "Analyze results"}
    ])
    state["plan_created"] = True
    return state

# === Workflow Graph Fixtures ===
@pytest.fixture
def compiled_test_graph(mock_llm):
    """Pre-compiled LangGraph for testing."""
    from app.domain.services.langgraph.graph import create_plan_act_graph
    return create_plan_act_graph(llm=mock_llm)

# === Tool Mock Factories ===
@pytest.fixture
def mock_tool_registry():
    """Registry of mock tools with configurable responses."""
    class MockToolRegistry:
        def __init__(self):
            self.tools = {}
            self.call_history = []

        def register(self, name: str, response: Any, error: Exception = None):
            self.tools[name] = {"response": response, "error": error}

        async def execute(self, name: str, args: dict):
            self.call_history.append({"tool": name, "args": args})
            tool = self.tools.get(name, {"response": "default"})
            if tool.get("error"):
                raise tool["error"]
            return tool["response"]

    return MockToolRegistry()
```

---

## Phase 1: Unit Tests - Agent Components

### 1.1 PlannerAgent Tests

**File:** `tests/unit/agents/test_planner.py`

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_simple_task_generates_1_to_3_steps` | Simple queries generate minimal plans | Steps count 1-3 |
| `test_complex_task_generates_5_to_12_steps` | Research tasks generate detailed plans | Steps count 5-12 |
| `test_plan_includes_required_fields` | All steps have action, description, tools | Schema validation passes |
| `test_empty_input_raises_error` | Empty user message handled | ValueError raised |
| `test_plan_respects_tool_constraints` | Plans only use available tools | Tool names validated |
| `test_plan_dependencies_ordered` | Dependent steps ordered correctly | Topological sort valid |
| `test_complexity_assessment_accurate` | Complexity matches task type | simple/medium/complex |
| `test_plan_with_context_injection` | Prior context affects planning | Context reflected in steps |

```python
# tests/unit/agents/test_planner.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.domain.services.agents.planner import PlannerAgent
from app.domain.models.plan import Plan, PlanStep

class TestPlannerAgent:
    """Unit tests for PlannerAgent."""

    @pytest.fixture
    def planner(self, mock_llm, mock_settings):
        return PlannerAgent(llm=mock_llm, settings=mock_settings)

    @pytest.mark.asyncio
    async def test_simple_task_generates_minimal_steps(
        self, planner, mock_llm_plan_response
    ):
        """Simple queries should generate 1-3 steps."""
        planner.llm.generate = AsyncMock(return_value=mock_llm_plan_response([
            {"step": 1, "action": "answer", "description": "Provide answer"}
        ]))

        plan = await planner.create_plan("What is 2+2?")

        assert len(plan.steps) <= 3
        assert plan.complexity == "simple"

    @pytest.mark.asyncio
    async def test_complex_task_generates_detailed_plan(
        self, planner, mock_llm_plan_response
    ):
        """Research tasks should generate 5-12 steps."""
        planner.llm.generate = AsyncMock(return_value=mock_llm_plan_response([
            {"step": i, "action": "research", "description": f"Step {i}"}
            for i in range(1, 8)
        ], complexity="complex"))

        plan = await planner.create_plan(
            "Research the latest AI developments and write a comprehensive report"
        )

        assert 5 <= len(plan.steps) <= 12
        assert plan.complexity == "complex"

    @pytest.mark.asyncio
    async def test_plan_schema_validation(self, planner, mock_llm_plan_response):
        """All steps must have required fields."""
        planner.llm.generate = AsyncMock(return_value=mock_llm_plan_response([
            {"step": 1, "action": "search", "description": "Search", "tools": ["web_search"]}
        ]))

        plan = await planner.create_plan("Find information about Python")

        for step in plan.steps:
            assert hasattr(step, "action")
            assert hasattr(step, "description")
            assert step.action is not None

    @pytest.mark.asyncio
    async def test_empty_input_raises_error(self, planner):
        """Empty user message should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            await planner.create_plan("")

    @pytest.mark.parametrize("task,expected_complexity", [
        ("What is Python?", "simple"),
        ("Compare Python and JavaScript for web development", "medium"),
        ("Research AI trends, analyze market data, and create investment report", "complex"),
    ])
    @pytest.mark.asyncio
    async def test_complexity_assessment(
        self, planner, mock_llm_plan_response, task, expected_complexity
    ):
        """Complexity should match task type."""
        planner.llm.generate = AsyncMock(return_value=mock_llm_plan_response(
            [{"step": 1, "action": "test"}],
            complexity=expected_complexity
        ))

        plan = await planner.create_plan(task)

        assert plan.complexity == expected_complexity
```

### 1.2 ExecutionAgent Tests

**File:** `tests/unit/agents/test_execution.py`

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_executes_single_tool_call` | Single tool executed correctly | Tool called with args |
| `test_parallel_tool_execution` | Multiple independent tools run parallel | Concurrent execution |
| `test_sequential_tool_execution` | Dependent tools run in order | Serial execution |
| `test_tool_error_triggers_retry` | Failed tools retry with backoff | 3 retries attempted |
| `test_max_iterations_enforced` | Execution stops at max iterations | 400 iterations max |
| `test_token_budget_respected` | Token limits enforced | Response truncated |
| `test_context_manager_limits` | Context window managed | 8000 token limit |
| `test_source_citation_tracking` | Citations extracted from results | Sources recorded |

```python
# tests/unit/agents/test_execution.py
import pytest
from unittest.mock import AsyncMock, patch
from app.domain.services.agents.execution import ExecutionAgent

class TestExecutionAgent:
    """Unit tests for ExecutionAgent."""

    @pytest.fixture
    def executor(self, mock_llm, mock_sandbox, mock_settings):
        return ExecutionAgent(
            llm=mock_llm,
            sandbox=mock_sandbox,
            settings=mock_settings
        )

    @pytest.mark.asyncio
    async def test_executes_single_tool_call(
        self, executor, mock_tool_registry
    ):
        """Single tool should be executed correctly."""
        mock_tool_registry.register("web_search", {"results": ["result1"]})
        executor.tool_registry = mock_tool_registry

        result = await executor.execute_step({
            "action": "search",
            "tool": "web_search",
            "args": {"query": "test"}
        })

        assert len(mock_tool_registry.call_history) == 1
        assert mock_tool_registry.call_history[0]["tool"] == "web_search"

    @pytest.mark.asyncio
    async def test_parallel_tool_execution(
        self, executor, mock_tool_registry
    ):
        """Independent tools should execute in parallel."""
        mock_tool_registry.register("search_a", {"data": "a"})
        mock_tool_registry.register("search_b", {"data": "b"})
        executor.tool_registry = mock_tool_registry

        with patch('asyncio.gather') as mock_gather:
            mock_gather.return_value = [{"data": "a"}, {"data": "b"}]

            await executor.execute_parallel_tools([
                {"tool": "search_a", "args": {}},
                {"tool": "search_b", "args": {}}
            ])

            mock_gather.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_error_triggers_retry(
        self, executor, mock_tool_registry
    ):
        """Failed tools should retry up to 3 times."""
        call_count = 0

        async def failing_tool(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return {"success": True}

        mock_tool_registry.execute = failing_tool
        executor.tool_registry = mock_tool_registry

        result = await executor.execute_step({
            "action": "test",
            "tool": "failing_tool",
            "args": {}
        })

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_iterations_enforced(self, executor):
        """Execution should stop at max iterations (400)."""
        executor.iteration_count = 399

        with pytest.raises(MaxIterationsError):
            await executor.execute_step({"action": "test"})
```

### 1.3 VerifierAgent Tests

**File:** `tests/unit/agents/test_verifier.py`

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_simple_plan_skips_verification` | Plans ≤2 steps skip verification | Skip flag set |
| `test_invalid_tool_fails_verification` | Unknown tools rejected | Verification fails |
| `test_missing_prerequisites_detected` | Missing prereqs flagged | Feedback provided |
| `test_dependency_cycle_detected` | Circular deps rejected | Error raised |
| `test_max_revision_loops` | Only 2 revision attempts | Loop count = 2 |
| `test_confidence_threshold` | Low confidence triggers revision | Threshold 0.6 |

```python
# tests/unit/agents/test_verifier.py
import pytest
from app.domain.services.agents.verifier import VerifierAgent

class TestVerifierAgent:
    """Unit tests for VerifierAgent."""

    @pytest.fixture
    def verifier(self, mock_llm, mock_settings):
        return VerifierAgent(llm=mock_llm, settings=mock_settings)

    @pytest.mark.asyncio
    async def test_simple_plan_skips_verification(self, verifier):
        """Plans with ≤2 steps should skip verification."""
        simple_plan = {"steps": [{"step": 1}, {"step": 2}]}

        result = await verifier.verify_plan(simple_plan)

        assert result.skipped is True
        assert result.verdict == "approved"

    @pytest.mark.asyncio
    async def test_invalid_tool_fails_verification(self, verifier):
        """Plans with unknown tools should fail."""
        invalid_plan = {
            "steps": [
                {"step": 1, "tool": "nonexistent_tool"}
            ]
        }

        result = await verifier.verify_plan(invalid_plan)

        assert result.verdict == "rejected"
        assert "unknown tool" in result.feedback.lower()

    @pytest.mark.asyncio
    async def test_dependency_cycle_detected(self, verifier):
        """Circular dependencies should be detected."""
        cyclic_plan = {
            "steps": [
                {"step": 1, "depends_on": [3]},
                {"step": 2, "depends_on": [1]},
                {"step": 3, "depends_on": [2]}
            ]
        }

        result = await verifier.verify_plan(cyclic_plan)

        assert result.verdict == "rejected"
        assert "cycle" in result.feedback.lower()
```

### 1.4 StuckDetector Tests

**File:** `tests/unit/agents/test_stuck_detector.py`

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_detects_exact_repetition` | Same output 3x detected | is_stuck = True |
| `test_detects_semantic_repetition` | Similar outputs detected | Similarity > 0.9 |
| `test_no_false_positive_on_progress` | Different outputs pass | is_stuck = False |
| `test_confidence_scoring` | Confidence reflects certainty | 0.0-1.0 range |
| `test_window_size_respected` | Only recent actions checked | Window = 5 |

```python
# tests/unit/agents/test_stuck_detector.py
import pytest
from app.domain.services.agents.stuck_detector import StuckDetector

class TestStuckDetector:
    """Unit tests for StuckDetector."""

    @pytest.fixture
    def detector(self):
        return StuckDetector(window_size=5, similarity_threshold=0.9)

    def test_detects_exact_repetition(self, detector):
        """Same output repeated 3+ times should be detected."""
        actions = [
            {"output": "searching..."},
            {"output": "searching..."},
            {"output": "searching..."},
        ]

        result = detector.check(actions)

        assert result.is_stuck is True
        assert result.confidence > 0.95

    def test_detects_semantic_repetition(self, detector):
        """Semantically similar outputs should be detected."""
        actions = [
            {"output": "I will search for information"},
            {"output": "Let me search for info"},
            {"output": "Searching for the information now"},
        ]

        result = detector.check(actions)

        assert result.is_stuck is True
        assert result.pattern_type == "semantic"

    def test_no_false_positive_on_progress(self, detector):
        """Different meaningful outputs should not trigger."""
        actions = [
            {"output": "Found 3 results"},
            {"output": "Analyzing first result"},
            {"output": "Extracting key information"},
        ]

        result = detector.check(actions)

        assert result.is_stuck is False

    @pytest.mark.parametrize("repetitions,expected_confidence", [
        (2, 0.5),
        (3, 0.75),
        (5, 0.95),
    ])
    def test_confidence_scaling(self, detector, repetitions, expected_confidence):
        """Confidence should scale with repetition count."""
        actions = [{"output": "same"} for _ in range(repetitions)]

        result = detector.check(actions)

        assert abs(result.confidence - expected_confidence) < 0.1
```

### 1.5 ReflectionAgent Tests

**File:** `tests/unit/agents/test_reflection.py`

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_continue_on_success` | Successful step continues | decision = "continue" |
| `test_adjust_on_partial_success` | Partial success adjusts | decision = "adjust" |
| `test_replan_on_failure` | Failed step triggers replan | decision = "replan" |
| `test_escalate_on_critical_error` | Critical errors escalate | decision = "escalate" |
| `test_stuck_detection_triggers_replan` | Stuck state triggers replan | decision = "replan" |

---

## Phase 2: Integration Tests - Workflow Pipelines

### 2.1 Plan-Execute Flow Integration

**File:** `tests/integration/test_plan_execute_flow.py`

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_simple_query_completes` | Simple Q&A flow | Response generated |
| `test_multi_step_plan_executes` | 3-step plan completes | All steps executed |
| `test_tool_failure_recovery` | Failed tool retries | Recovery succeeds |
| `test_verification_feedback_loop` | Invalid plan revised | Plan updated |
| `test_reflection_triggers_adjustment` | Poor result adjusts | Approach changed |
| `test_stuck_detection_triggers_replan` | Loop detected | New plan created |

```python
# tests/integration/test_plan_execute_flow.py
import pytest
from app.domain.services.flows.plan_act import PlanActFlow

class TestPlanExecuteFlowIntegration:
    """Integration tests for Plan-Execute workflow."""

    @pytest.fixture
    def flow(self, mock_llm, mock_sandbox, mock_settings):
        return PlanActFlow(
            llm=mock_llm,
            sandbox=mock_sandbox,
            settings=mock_settings
        )

    @pytest.mark.asyncio
    async def test_simple_query_completes_without_planning(self, flow):
        """Simple queries should use fast path."""
        result = await flow.run("What is 2+2?")

        assert result.success is True
        assert result.used_fast_path is True
        assert "4" in result.response

    @pytest.mark.asyncio
    async def test_multi_step_plan_executes_all_steps(
        self, flow, mock_llm_plan_response
    ):
        """Multi-step plans should execute all steps."""
        flow.planner.llm.generate = AsyncMock(return_value=mock_llm_plan_response([
            {"step": 1, "action": "search", "tool": "web_search"},
            {"step": 2, "action": "analyze", "tool": "none"},
            {"step": 3, "action": "summarize", "tool": "none"}
        ]))

        result = await flow.run("Research Python trends and summarize")

        assert result.success is True
        assert result.steps_completed == 3

    @pytest.mark.asyncio
    async def test_tool_failure_triggers_retry(
        self, flow, mock_tool_registry
    ):
        """Failed tools should be retried before failing."""
        fail_count = [0]

        async def flaky_tool(*args, **kwargs):
            fail_count[0] += 1
            if fail_count[0] < 2:
                raise Exception("Network error")
            return {"data": "success"}

        mock_tool_registry.execute = flaky_tool
        flow.tool_registry = mock_tool_registry

        result = await flow.run("Search for information")

        assert result.success is True
        assert fail_count[0] >= 2  # At least one retry

    @pytest.mark.asyncio
    async def test_verification_feedback_revises_plan(self, flow):
        """Verification feedback should trigger plan revision."""
        # First plan has issues
        flow.planner.create_plan = AsyncMock(side_effect=[
            {"steps": [{"step": 1, "tool": "unknown"}]},  # Invalid
            {"steps": [{"step": 1, "tool": "web_search"}]}  # Valid
        ])

        result = await flow.run("Search for something")

        assert result.success is True
        assert flow.planner.create_plan.call_count == 2

    @pytest.mark.asyncio
    async def test_stuck_detection_triggers_new_strategy(self, flow):
        """Stuck detection should trigger strategy change."""
        # Simulate stuck state
        flow.executor.execute_step = AsyncMock(side_effect=[
            {"output": "searching..."},
            {"output": "searching..."},
            {"output": "searching..."},
            {"output": "Found results!"}  # Eventually succeeds
        ])

        result = await flow.run("Find information")

        assert result.stuck_detected is True
        assert result.success is True
```

### 2.2 LangGraph Workflow Integration

**File:** `tests/integration/test_langgraph_workflow.py`

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_graph_compilation` | Graph compiles without error | Compiled graph |
| `test_planning_node_creates_plan` | Planning node produces plan | State has plan |
| `test_execution_node_runs_tools` | Execution node calls tools | Tools executed |
| `test_reflection_node_analyzes` | Reflection node decides | Decision made |
| `test_state_persistence` | State persists across nodes | State consistent |
| `test_routing_logic` | Conditional edges route correctly | Correct path |
| `test_checkpoint_recovery` | Workflow resumes from checkpoint | State restored |

```python
# tests/integration/test_langgraph_workflow.py
import pytest
from langgraph.checkpoint.memory import MemorySaver
from app.domain.services.langgraph.graph import create_plan_act_graph
from app.domain.services.langgraph.state import PlanActState

class TestLangGraphWorkflowIntegration:
    """Integration tests for LangGraph workflow."""

    @pytest.fixture
    def graph(self, mock_llm, mock_sandbox):
        return create_plan_act_graph(
            llm=mock_llm,
            sandbox=mock_sandbox,
            checkpointer=MemorySaver()
        )

    @pytest.mark.asyncio
    async def test_graph_compiles_successfully(self, graph):
        """Graph should compile without errors."""
        compiled = graph.compile()

        assert compiled is not None
        assert hasattr(compiled, 'invoke')

    @pytest.mark.asyncio
    async def test_planning_node_creates_plan(
        self, graph, initial_plan_act_state
    ):
        """Planning node should populate plan in state."""
        compiled = graph.compile()

        result = await compiled.ainvoke(
            initial_plan_act_state,
            config={"configurable": {"thread_id": "test-1"}}
        )

        assert result["plan"] is not None
        assert result["plan_created"] is True

    @pytest.mark.asyncio
    async def test_state_transitions_correctly(
        self, graph, initial_plan_act_state
    ):
        """State should transition through all phases."""
        compiled = graph.compile()
        states = []

        async for state in compiled.astream(
            initial_plan_act_state,
            config={"configurable": {"thread_id": "test-2"}}
        ):
            states.append(state)

        # Verify state progression
        assert any(s.get("plan_created") for s in states)
        assert any(s.get("all_steps_done") for s in states)

    @pytest.mark.asyncio
    async def test_routing_follows_conditions(
        self, graph, state_with_plan
    ):
        """Routing should follow conditional edges."""
        compiled = graph.compile()

        # Add error to state to test error routing
        state_with_plan["error"] = "Test error"
        state_with_plan["error_count"] = 1

        result = await compiled.ainvoke(
            state_with_plan,
            config={"configurable": {"thread_id": "test-3"}}
        )

        # Should have attempted recovery
        assert result.get("recovery_attempts", 0) > 0

    @pytest.mark.asyncio
    async def test_checkpoint_enables_resume(self, graph, initial_plan_act_state):
        """Workflow should resume from checkpoint."""
        compiled = graph.compile()
        thread_id = "test-checkpoint"

        # Run partially
        result1 = await compiled.ainvoke(
            initial_plan_act_state,
            config={"configurable": {"thread_id": thread_id}}
        )

        # Get checkpoint state
        checkpoint = compiled.get_state(
            config={"configurable": {"thread_id": thread_id}}
        )

        # Resume should continue from checkpoint
        result2 = await compiled.ainvoke(
            None,  # No new input, resume from checkpoint
            config={"configurable": {"thread_id": thread_id}}
        )

        assert result2["iteration_count"] >= result1["iteration_count"]
```

### 2.3 Error Recovery Integration

**File:** `tests/integration/test_error_recovery.py`

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_transient_error_retry` | Network errors retry | Retry succeeds |
| `test_permanent_error_escalation` | Auth errors escalate | User notified |
| `test_tool_error_isolation` | One tool failure doesn't halt | Other tools run |
| `test_cascade_prevention` | Error cascade prevented | Controlled failure |
| `test_graceful_degradation` | Partial success accepted | Best effort result |

---

## Phase 3: End-to-End Tests - Complete Flows

### 3.1 Simple Tasks E2E

**File:** `tests/e2e/test_simple_tasks.py`

| Test Case | Description | LLM Mode | Expected |
|-----------|-------------|----------|----------|
| `test_direct_qa` | "What is Python?" | Real | Answer contains "programming" |
| `test_calculation` | "Calculate 15% of 200" | Real | Answer is "30" |
| `test_definition` | "Define machine learning" | Real | Definition provided |
| `test_comparison` | "Compare X vs Y" | Real | Both compared |

```python
# tests/e2e/test_simple_tasks.py
import pytest
from app.domain.services.flows.plan_act import PlanActFlow

@pytest.mark.e2e
@pytest.mark.slow
class TestSimpleTasksE2E:
    """End-to-end tests with real LLM for simple tasks."""

    @pytest.fixture
    def flow(self, real_llm, real_sandbox, settings):
        return PlanActFlow(
            llm=real_llm,
            sandbox=real_sandbox,
            settings=settings
        )

    @pytest.mark.asyncio
    async def test_direct_qa_answers_correctly(self, flow):
        """Direct questions should be answered accurately."""
        result = await flow.run("What is the capital of France?")

        assert result.success is True
        assert "Paris" in result.response

    @pytest.mark.asyncio
    async def test_calculation_is_accurate(self, flow):
        """Calculations should be correct."""
        result = await flow.run("What is 15% of 200?")

        assert result.success is True
        assert "30" in result.response

    @pytest.mark.asyncio
    async def test_fast_path_used_for_simple_queries(self, flow):
        """Simple queries should use fast path."""
        result = await flow.run("Hello, how are you?")

        assert result.used_fast_path is True
        assert result.steps_executed == 0
```

### 3.2 Complex Research E2E

**File:** `tests/e2e/test_complex_research.py`

| Test Case | Description | LLM Mode | Expected |
|-----------|-------------|----------|----------|
| `test_web_research` | "Research latest AI trends" | Real | Sources cited |
| `test_multi_step_analysis` | "Analyze and compare X, Y, Z" | Real | Comparison table |
| `test_data_synthesis` | "Gather data and summarize" | Real | Summary provided |

### 3.3 Tool-Heavy Tasks E2E

**File:** `tests/e2e/test_tool_heavy_tasks.py`

| Test Case | Description | Tools Used | Expected |
|-----------|-------------|------------|----------|
| `test_file_operations` | "Create and edit file" | file_write, file_read | File created |
| `test_code_execution` | "Run Python script" | shell, code_executor | Output captured |
| `test_browser_automation` | "Navigate and extract" | browser | Data extracted |

---

## Phase 4: Evaluation Framework - LLM Quality

### 4.1 Evaluation Datasets

**File:** `tests/evals/datasets/planning_cases.json`

```json
{
  "cases": [
    {
      "id": "plan_001",
      "input": "Research Python async patterns",
      "constraints": {
        "min_steps": 2,
        "max_steps": 6,
        "required_tools": ["web_search"],
        "complexity": "medium"
      },
      "tags": ["planning", "research"]
    },
    {
      "id": "plan_002",
      "input": "What is 2+2?",
      "constraints": {
        "max_steps": 1,
        "complexity": "simple",
        "fast_path_expected": true
      },
      "tags": ["planning", "simple"]
    }
  ]
}
```

### 4.2 Grader Implementations

**File:** `tests/evals/graders/deterministic.py`

```python
# tests/evals/graders/deterministic.py
from dataclasses import dataclass
from typing import Any

@dataclass
class GradeResult:
    passed: bool
    score: float
    feedback: str

class DeterministicGrader:
    """Rule-based grading for deterministic checks."""

    def grade_plan_structure(self, plan: dict, constraints: dict) -> GradeResult:
        """Check plan meets structural constraints."""
        steps = plan.get("steps", [])

        # Check step count
        min_steps = constraints.get("min_steps", 1)
        max_steps = constraints.get("max_steps", 20)

        if not (min_steps <= len(steps) <= max_steps):
            return GradeResult(
                passed=False,
                score=0.0,
                feedback=f"Step count {len(steps)} outside range [{min_steps}, {max_steps}]"
            )

        # Check required tools
        required_tools = constraints.get("required_tools", [])
        plan_tools = {step.get("tool") for step in steps if step.get("tool")}

        missing_tools = set(required_tools) - plan_tools
        if missing_tools:
            return GradeResult(
                passed=False,
                score=0.5,
                feedback=f"Missing required tools: {missing_tools}"
            )

        return GradeResult(passed=True, score=1.0, feedback="Plan structure valid")

    def grade_execution_result(self, result: dict, expected: dict) -> GradeResult:
        """Check execution result meets expectations."""
        # Check success
        if not result.get("success") and expected.get("should_succeed", True):
            return GradeResult(
                passed=False,
                score=0.0,
                feedback="Execution failed unexpectedly"
            )

        # Check required content
        required_content = expected.get("contains", [])
        response = result.get("response", "").lower()

        missing = [c for c in required_content if c.lower() not in response]
        if missing:
            return GradeResult(
                passed=False,
                score=0.7,
                feedback=f"Missing required content: {missing}"
            )

        return GradeResult(passed=True, score=1.0, feedback="Result valid")
```

**File:** `tests/evals/graders/llm_judge.py`

```python
# tests/evals/graders/llm_judge.py
from dataclasses import dataclass

@dataclass
class LLMJudgeResult:
    passed: bool
    score: float
    reasoning: str
    criteria_scores: dict

class LLMJudge:
    """LLM-based grading for subjective quality assessment."""

    def __init__(self, llm, criteria: list[str] = None):
        self.llm = llm
        self.criteria = criteria or [
            "relevance",
            "accuracy",
            "completeness",
            "coherence"
        ]

    async def grade_response(
        self,
        query: str,
        response: str,
        context: str = ""
    ) -> LLMJudgeResult:
        """Grade response quality using LLM."""
        prompt = f"""
You are an expert evaluator. Grade the following response.

Query: {query}
{f"Context: {context}" if context else ""}
Response: {response}

Grade each criterion from 0-10:
- Relevance: Does the response address the query?
- Accuracy: Is the information correct?
- Completeness: Is the response thorough?
- Coherence: Is the response well-organized?

Output JSON:
{{
  "relevance": <score>,
  "accuracy": <score>,
  "completeness": <score>,
  "coherence": <score>,
  "overall": <average>,
  "reasoning": "<explanation>"
}}
"""
        result = await self.llm.generate(prompt)
        scores = self._parse_scores(result)

        return LLMJudgeResult(
            passed=scores["overall"] >= 7.0,
            score=scores["overall"] / 10.0,
            reasoning=scores["reasoning"],
            criteria_scores=scores
        )

    async def grade_plan_quality(
        self,
        task: str,
        plan: dict
    ) -> LLMJudgeResult:
        """Grade plan quality for a given task."""
        prompt = f"""
You are an expert evaluator. Grade this execution plan.

Task: {task}
Plan: {plan}

Grade each criterion from 0-10:
- Feasibility: Can this plan realistically complete the task?
- Efficiency: Is the plan optimally structured?
- Completeness: Does the plan cover all aspects?
- Tool_Usage: Are the right tools selected?

Output JSON with scores and reasoning.
"""
        result = await self.llm.generate(prompt)
        scores = self._parse_scores(result)

        return LLMJudgeResult(
            passed=scores["overall"] >= 7.0,
            score=scores["overall"] / 10.0,
            reasoning=scores["reasoning"],
            criteria_scores=scores
        )
```

### 4.3 Benchmark Suite

**File:** `tests/evals/benchmarks/accuracy_benchmark.py`

```python
# tests/evals/benchmarks/accuracy_benchmark.py
import asyncio
from dataclasses import dataclass
from typing import List

@dataclass
class BenchmarkResult:
    total_cases: int
    passed_cases: int
    pass_rate: float
    avg_score: float
    latency_p50: float
    latency_p95: float
    cost_total: float
    failures: List[dict]

class AccuracyBenchmark:
    """Benchmark for measuring agent accuracy."""

    def __init__(self, flow, graders: list):
        self.flow = flow
        self.graders = graders

    async def run(self, cases: list[dict]) -> BenchmarkResult:
        """Run benchmark on all cases."""
        results = []

        for case in cases:
            result = await self._evaluate_case(case)
            results.append(result)

        return self._aggregate_results(results)

    async def _evaluate_case(self, case: dict) -> dict:
        """Evaluate a single test case."""
        import time

        start = time.time()
        output = await self.flow.run(case["input"])
        latency = time.time() - start

        # Apply all graders
        grades = []
        for grader in self.graders:
            grade = await grader.grade(output, case)
            grades.append(grade)

        return {
            "case_id": case["id"],
            "passed": all(g.passed for g in grades),
            "score": sum(g.score for g in grades) / len(grades),
            "latency": latency,
            "cost": output.get("cost", 0),
            "grades": grades
        }

    def _aggregate_results(self, results: list) -> BenchmarkResult:
        """Aggregate individual results into benchmark result."""
        passed = [r for r in results if r["passed"]]
        latencies = sorted([r["latency"] for r in results])

        return BenchmarkResult(
            total_cases=len(results),
            passed_cases=len(passed),
            pass_rate=len(passed) / len(results) if results else 0,
            avg_score=sum(r["score"] for r in results) / len(results) if results else 0,
            latency_p50=latencies[len(latencies) // 2] if latencies else 0,
            latency_p95=latencies[int(len(latencies) * 0.95)] if latencies else 0,
            cost_total=sum(r["cost"] for r in results),
            failures=[r for r in results if not r["passed"]]
        )
```

### 4.4 Metrics Reference

| Metric Category | Metric | Description | Target |
|-----------------|--------|-------------|--------|
| **Accuracy** | Task Completion | % tasks completed successfully | >90% |
| **Accuracy** | Plan Quality | LLM judge score for plans | >7.0/10 |
| **Accuracy** | Response Relevance | Answer addresses query | >8.0/10 |
| **Accuracy** | Hallucination Rate | % responses with false info | <5% |
| **Performance** | Latency P50 | Median response time | <30s |
| **Performance** | Latency P95 | 95th percentile response | <120s |
| **Performance** | Token Efficiency | Tokens per successful task | <10k |
| **Reliability** | Error Recovery Rate | % errors recovered | >80% |
| **Reliability** | Stuck Detection Rate | % stuck states detected | >95% |
| **Safety** | Security Flag Rate | % unsafe actions caught | 100% |

---

## Phase 5: Regression & CI/CD Integration

### 5.1 Test Markers

```python
# pytest.ini
[pytest]
markers =
    unit: Unit tests (fast, mocked)
    integration: Integration tests (medium, partially mocked)
    e2e: End-to-end tests (slow, real LLM)
    eval: Evaluation tests (variable, benchmarks)
    slow: Tests that take >30 seconds
    flaky: Tests with non-deterministic behavior

testpaths = tests
asyncio_mode = auto
```

### 5.2 CI Pipeline Configuration

```yaml
# .github/workflows/agent-tests.yml
name: Agent Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Unit Tests
        run: |
          cd backend
          pytest tests/unit -v --tb=short -x

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - name: Run Integration Tests
        run: |
          cd backend
          pytest tests/integration -v --tb=short

  e2e-tests:
    runs-on: ubuntu-latest
    needs: integration-tests
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Run E2E Tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          cd backend
          pytest tests/e2e -v --tb=long -x

  eval-benchmarks:
    runs-on: ubuntu-latest
    needs: integration-tests
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Run Evaluation Benchmarks
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          cd backend
          python -m tests.evals.eval_runner --output reports/eval_report.json
      - name: Upload Results
        uses: actions/upload-artifact@v4
        with:
          name: eval-reports
          path: reports/
```

### 5.3 Pre-commit Hooks

```yaml
# .pre-commit-config.yaml (addition)
repos:
  - repo: local
    hooks:
      - id: agent-unit-tests
        name: Run Agent Unit Tests
        entry: bash -c 'cd backend && pytest tests/unit -x -q'
        language: system
        pass_filenames: false
        files: ^backend/app/domain/services/agents/
```

---

## Implementation Schedule

### Week 1: Foundation

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Set up test directory structure | Directories created |
| 1 | Enhance conftest.py with new fixtures | Fixtures ready |
| 2 | Implement PlannerAgent unit tests | `test_planner.py` |
| 3 | Implement ExecutionAgent unit tests | `test_execution.py` |
| 4 | Implement VerifierAgent unit tests | `test_verifier.py` |
| 5 | Implement StuckDetector unit tests | `test_stuck_detector.py` |

### Week 2: Integration

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Plan-Execute flow integration tests | `test_plan_execute_flow.py` |
| 2 | LangGraph workflow integration tests | `test_langgraph_workflow.py` |
| 3 | Error recovery integration tests | `test_error_recovery.py` |
| 4 | Memory integration tests | `test_memory_integration.py` |
| 5 | Multi-agent handoff tests | `test_multi_agent_handoff.py` |

### Week 3: E2E & Evals

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Simple tasks E2E tests | `test_simple_tasks.py` |
| 2 | Complex research E2E tests | `test_complex_research.py` |
| 3 | Tool-heavy tasks E2E tests | `test_tool_heavy_tasks.py` |
| 4 | Implement deterministic graders | `graders/deterministic.py` |
| 5 | Implement LLM judge grader | `graders/llm_judge.py` |

### Week 4: Benchmarks & CI

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Create evaluation datasets | `datasets/*.json` |
| 2 | Implement accuracy benchmark | `benchmarks/accuracy_benchmark.py` |
| 3 | Implement latency benchmark | `benchmarks/latency_benchmark.py` |
| 4 | Set up CI pipeline | `.github/workflows/agent-tests.yml` |
| 5 | Documentation & cleanup | README, final review |

---

## Success Criteria

### Coverage Targets

| Test Type | Target Coverage | Current |
|-----------|----------------|---------|
| Unit Tests | >80% line coverage | TBD |
| Integration Tests | >70% workflow coverage | TBD |
| E2E Tests | 10 core scenarios | TBD |
| Eval Cases | 50+ test cases | TBD |

### Quality Targets

| Metric | Target | Current |
|--------|--------|---------|
| Task Completion Rate | >90% | TBD |
| Avg Response Score | >7.5/10 | TBD |
| P95 Latency | <120s | TBD |
| Error Recovery Rate | >80% | TBD |

---

## References

- [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [LangGraph Testing Documentation](https://docs.langchain.com/oss/python/langgraph/test)
- [DeepEval: LLM Testing Framework](https://github.com/confident-ai/deepeval)
- [Confident AI: LLM Testing Best Practices 2026](https://www.confident-ai.com/blog/llm-testing-in-2024-top-methods-and-strategies)
- [Future AGI: LLM Evaluation Guide 2026](https://futureagi.substack.com/p/llm-evaluation-frameworks-metrics)
