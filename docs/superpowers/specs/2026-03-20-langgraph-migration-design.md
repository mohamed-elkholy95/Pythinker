# LangGraph Migration Design Spec

**Date**: 2026-03-20
**Status**: Draft
**Author**: Mohamed Elkholy
**Scope**: Replace Pythinker's hand-rolled agent orchestration (~50 files, ~15,000 lines) with LangGraph

---

## 1. Problem Statement

Pythinker's agent system is a hand-rolled, 150+ file implementation spanning domain services, flows, monitors, detectors, middleware, and a custom LLM integration layer. The system works but has become difficult to maintain and extend:

- **6+ files** for the core execution loop (`base.py`, `execution.py`, middleware pipeline, monitors)
- **35+ files** in `domain/services/flows/` for workflow orchestration
- **8+ files** in `infrastructure/external/llm/` for provider integration
- No crash recovery or durable execution
- No native human-in-the-loop support
- Custom state management scattered across multiple classes

The goal is to replace this with LangGraph, a production-grade agent orchestration framework that provides state machines, checkpointing, streaming, and ReAct agents out of the box.

## 2. Decision Record

### Why LangGraph over CrewAI

| Factor | LangGraph | CrewAI |
|--------|-----------|--------|
| Async-native (FastAPI compat) | Yes | No (thread-wrapped) |
| Checkpointing/crash recovery | Built-in (MongoDB) | None |
| HITL support | Native interrupt/resume | None |
| Streaming modes | `astream_events()` maps to SSE | Thread-based, awkward |
| MongoDB integration | `langgraph-checkpoint-mongodb` | Not integrated |
| Maturity | GA 1.0 (Oct 2025) | v1.10, fast-moving |

### Why LangGraph over keeping the current system

- **10x reduction**: ~50 files / ~15,000 lines replaced by ~15 files / ~1,500 lines
- **Crash recovery for free**: MongoDB checkpointer saves state after every node
- **HITL for free**: `interrupt()` / `Command(resume=)` pattern
- **Time-travel debugging**: Replay from any checkpoint
- **Community-maintained**: ReAct loop, tool dispatch, state management maintained by LangChain team

### Accepted tradeoffs

- **Dependency on `langchain-core`**: LangGraph requires it. LangChain-specific message/tool formats.
- **LangGraph 2.0 risk**: Breaking changes expected Q2 2026. Mitigated by strict version pinning.
- **Lost custom capabilities**: JSON repair for GLM, API key pool rotation, provider auto-detection, analysis paralysis detection, truncation detection. These either get reimplemented as LangGraph callbacks or dropped.
- **LangSmith push**: Best observability requires LangSmith (paid). OpenTelemetry works but is less integrated. Aligns with self-hosted-first principle to use OTEL.

## 3. Architecture Overview

### What stays (untouched)

| Layer | Components |
|-------|-----------|
| Frontend | Vue 3 app, SSE consumer, all components |
| API routes | FastAPI endpoints (SSE endpoint adapts) |
| Infrastructure | MongoDB, Redis, Qdrant, Sandbox implementation |
| Domain protocols | `Sandbox`, `Browser` protocols |
| Domain models | `Session`, `Event`, `ToolResult` (simplified) |
| Core | Config, SandboxManager, SandboxPool |
| Tools | All 17+ tool classes (`ShellTool`, `BrowserTool`, `FileTool`, etc.) |

### What gets deleted (~50 files, ~15,000 lines)

#### Agent services (`domain/services/agents/`)
- `base.py` — ReAct loop, middleware pipeline integration
- `execution.py` — Execution agent, summarization
- `planner.py` — Planner agent
- `verifier.py` — Verifier agent
- `critic.py`, `critic_agent.py` — Critic agents
- `reflective_executor.py` — Reflection loops
- `output_verifier.py` — Output hallucination checking
- `grounding_validator.py` — Source grounding validation
- `hallucination_detector.py` — Tool call hallucination detection
- `security_assessor.py` — Security assessment middleware
- `tool_efficiency_monitor.py` — Analysis paralysis detection
- `truncation_detector.py` — Incomplete output detection
- `stuck_detector.py` — Repeated output detection
- `middleware_pipeline.py` — Middleware chain
- `model_router.py` — Adaptive model routing
- `complexity_assessor.py` — Task complexity scoring
- `document_segmenter.py` — AST-aware document chunking
- `implementation_tracker.py` — Multi-file code completeness
- `context_manager.py` — Execution context management
- `token_manager.py` — Token counting per model
- `token_budget_manager.py` — Phase-level token budget
- `sliding_window_context.py` — Long context compression
- `memory_manager.py` — Memory compaction
- `prompt_cache_manager.py` — Anthropic prompt caching
- `step_executor.py` — Step-level tracking
- `step_context_assembler.py` — Prompt context assembly
- `error_handler.py` — Error classification and retry
- `url_failure_guard.py` — URL failure tracking
- `intent_classifier.py` — Intent classification

#### Flows (`domain/services/flows/`)
- `plan_act.py` — Main 4-phase flow orchestrator
- `discuss.py` — Simple Q&A flow
- `fast_search.py` — Search-only flow
- `flow_step_executor.py` — Step dispatch with phase routing
- `phase_router.py` — Phase-to-executor routing
- `step_failure.py` — Step failure recovery
- `fast_path.py` — Trivial query short-circuit
- All other flow files in the directory

#### Other domain files
- `agent_task_runner.py` — Task runner / flow selector
- `domain/models/plan.py` — Plan, Phase, Step models
- `domain/models/tool_name.py` — 107+ tool name enum
- `domain/models/state_manifest.py` — Blackboard for cross-agent state

#### LLM layer (`infrastructure/external/llm/`)
- `openai_llm.py` — OpenAI-compatible LLM (700+ lines)
- `anthropic_llm.py` — Anthropic native API
- `ollama_llm.py` — Local Ollama
- `universal_llm.py` — Provider auto-detection
- `instructor_adapter.py` — Instructor integration
- `json_repair.py` — Malformed JSON recovery
- `message_normalizer.py` — Cross-provider message normalization
- `factory.py` — LLM provider registry and factory

### What gets created (~15 files, ~1,500 lines)

```
domain/services/graphs/
  ├── state.py                    # AgentState TypedDict
  ├── agent_graph.py              # Main StateGraph definition
  ├── checkpointer.py             # MongoDB checkpointer config
  ├── nodes/
  │   ├── __init__.py
  │   ├── planning.py             # Planning node
  │   ├── execution.py            # Execution node (ReAct subgraph)
  │   ├── verification.py         # Verification node
  │   ├── summarization.py        # Summarization node
  │   ├── discuss.py              # Simple Q&A node
  │   ├── fast_search.py          # Search-only node
  │   └── routing.py              # Conditional edge functions
  └── callbacks.py                # Optional: custom callback handlers
domain/services/tools/
  └── langchain_adapters.py       # BaseTool → StructuredTool adapters
infrastructure/external/llm/
  └── langchain_llm.py            # ChatOpenAI factory for all providers
application/services/
  └── event_mapper.py             # LangGraph events → Pythinker SSE events
```

### What gets modified (~5 files)

| File | Change |
|------|--------|
| `interfaces/api/session_routes.py` | SSE endpoint calls `graph.astream_events()` via event mapper |
| `application/services/agent_service.py` | Simplified: builds graph, invokes, streams |
| `domain/services/agent_domain_service.py` | Simplified: delegates to graph |
| `core/config_llm.py` | Keep settings, remove provider-specific logic |
| `requirements.txt` | Add langgraph, langchain-core, langchain-openai; remove instructor |

## 4. Component Designs

### 4.1 State Schema

```python
# domain/services/graphs/state.py
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """Central state flowing through the agent graph."""

    # Core conversation — add_messages reducer appends and deduplicates by ID
    messages: Annotated[list[AnyMessage], add_messages]

    # Session context
    session_id: str
    sandbox_id: str | None

    # Flow routing — determined at entry
    mode: str  # "agent" | "discuss" | "fast_search"

    # Planning — populated by planning node, consumed by execution
    plan: dict | None
    current_step_index: int

    # Execution results — accumulated across steps
    step_results: list[dict]
    final_report: str

    # Safety controls — iteration_count tracks total steps executed across
    # all plan cycles (including replans). max_iterations caps total steps,
    # not replan cycles. E.g., max_iterations=20 allows at most 20 step
    # executions total, whether from one plan or multiple replans.
    iteration_count: int
    max_iterations: int
```

**Design notes:**
- `TypedDict` (not Pydantic) because LangGraph serializes state through checkpointers, and TypedDicts serialize cleanly.
- `Annotated[list, add_messages]` is LangGraph's built-in message reducer: node returns `{"messages": [new_msg]}` appends rather than overwrites, and deduplicates by message ID.
- `plan` is a plain `dict` rather than a Pydantic `Plan` model for checkpoint serialization compatibility.

### 4.2 Main Graph

```python
# domain/services/graphs/agent_graph.py
from langgraph.graph import StateGraph, START, END

from app.domain.services.graphs.checkpointer import get_checkpointer
from app.domain.services.graphs.nodes.discuss import discuss_node
from app.domain.services.graphs.nodes.execution import execution_node
from app.domain.services.graphs.nodes.fast_search import fast_search_node
from app.domain.services.graphs.nodes.planning import planning_node
from app.domain.services.graphs.nodes.routing import mode_router, step_router, verify_router
from app.domain.services.graphs.nodes.summarization import summarize_node
from app.domain.services.graphs.nodes.verification import verification_node
from app.domain.services.graphs.state import AgentState


async def build_agent_graph(tools, llm, sandbox):
    """Build the main agent workflow graph.

    Graph topology:
        START →  plan         (mode="agent")
              →  discuss      (mode="discuss")
              →  fast_search  (mode="fast_search")
        plan → execute_step
        execute_step → execute_step  (next step)
                     → verify        (all steps done)
                     → summarize     (max iterations)
        verify → summarize  (passed)
               → plan       (replan)
        summarize → END
        discuss   → END
        fast_search → END
    """
    workflow = StateGraph(AgentState)

    # Register nodes (using closure factories for dependency injection)
    workflow.add_node("plan", make_planning_node(llm))
    workflow.add_node("execute_step", make_execution_node(llm, tools))
    workflow.add_node("verify", make_verification_node(llm))
    workflow.add_node("summarize", make_summarize_node(llm))
    workflow.add_node("discuss", make_discuss_node(llm))
    workflow.add_node("fast_search", make_fast_search_node(llm, tools))

    # Entry: route directly from START based on mode (no pass-through node)
    workflow.add_conditional_edges(START, mode_router, {
        "agent": "plan",
        "discuss": "discuss",
        "fast_search": "fast_search",
    })

    # Agent flow edges
    workflow.add_edge("plan", "execute_step")
    workflow.add_conditional_edges("execute_step", step_router, {
        "next_step": "execute_step",
        "verify": "verify",
        "max_iter": "summarize",
    })
    workflow.add_conditional_edges("verify", verify_router, {
        "passed": "summarize",
        "replan": "plan",
    })

    # Terminal edges
    workflow.add_edge("summarize", END)
    workflow.add_edge("discuss", END)
    workflow.add_edge("fast_search", END)

    checkpointer = await get_checkpointer()
    return workflow.compile(checkpointer=checkpointer)
```

### 4.3 Routing Functions

```python
# domain/services/graphs/nodes/routing.py
from typing import Literal
from app.domain.services.graphs.state import AgentState


def mode_router(state: AgentState) -> Literal["agent", "discuss", "fast_search"]:
    """Route to the correct subflow based on mode.

    Used as a conditional edge directly from START — no pass-through node needed.
    """
    return state["mode"]


def step_router(state: AgentState) -> Literal["next_step", "verify", "max_iter"]:
    """Decide whether to execute next step, verify, or exit.

    iteration_count tracks total steps executed (across all plan cycles).
    max_iterations caps total steps to prevent runaway execution —
    whether from one plan with many steps or infinite replan loops.
    """
    if state["iteration_count"] >= state["max_iterations"]:
        return "max_iter"
    if state["plan"] and state["current_step_index"] < len(state["plan"]["steps"]):
        return "next_step"
    return "verify"


def verify_router(state: AgentState) -> Literal["passed", "replan"]:
    """Route based on verification result."""
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "content") and "REPLAN" in str(last_msg.content):
        return "replan"
    return "passed"
```

**Note**: The `route` node from the graph topology is eliminated — `mode_router` is used as a conditional edge directly from `START`:

```python
workflow.add_conditional_edges(START, mode_router, {
    "agent": "plan",
    "discuss": "discuss",
    "fast_search": "fast_search",
})
```

### 4.4 Execution Node (ReAct Agent)

**IMPORTANT**: LangGraph node functions receive exactly one argument — the state dict
(or state + `RunnableConfig`). Extra parameters like `llm` and `tools` must be bound
at graph-build time via closures, not passed as node function arguments.

```python
# domain/services/graphs/nodes/execution.py
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from app.domain.services.graphs.state import AgentState


def make_execution_node(llm, tools):
    """Factory that returns an execution node function with llm/tools bound via closure.

    LangGraph calls node functions as node_fn(state). We use a closure
    to capture llm and tools at graph-build time.

    Replaces: BaseAgent.execute() ReAct loop (400 lines),
    MiddlewarePipeline (5 middleware classes), all monitors.
    """
    react_agent = create_react_agent(model=llm, tools=tools)

    async def execution_node(state: AgentState) -> dict:
        """Execute current plan step via ReAct agent.

        Each invocation handles one step. The step_router conditional edge
        loops back to this node for the next step.

        To avoid message bloat, we only surface a summary of the ReAct
        agent's work back into the parent graph state, not all intermediate
        tool-call messages.
        """
        step = state["plan"]["steps"][state["current_step_index"]]
        step_instruction = HumanMessage(
            content=f"Execute this step: {step['description']}\n\nContext: {step.get('context', '')}"
        )

        result = await react_agent.ainvoke({
            "messages": state["messages"] + [step_instruction]
        })

        # Summarize: only surface the final assistant message, not all
        # intermediate tool calls, to prevent checkpoint bloat and
        # context window exhaustion on subsequent LLM calls.
        final_messages = [m for m in result["messages"] if isinstance(m, AIMessage) and not m.tool_calls]
        summary_msg = final_messages[-1] if final_messages else AIMessage(content="Step completed.")

        return {
            "messages": [summary_msg],  # Reducer appends this single summary
            "step_results": state["step_results"] + [{
                "step_index": state["current_step_index"],
                "description": step["description"],
                "status": "completed",
            }],
            "current_step_index": state["current_step_index"] + 1,
            "iteration_count": state["iteration_count"] + 1,
        }

    return execution_node
```

**Usage in graph builder** (closure binding pattern):

```python
# In agent_graph.py
workflow.add_node("execute_step", make_execution_node(llm, tools))
workflow.add_node("plan", make_planning_node(llm))
workflow.add_node("verify", make_verification_node(llm))
```

All node factories follow this same closure pattern — `make_*_node(deps)` returns
an `async def node(state) -> dict` function with dependencies captured.

### 4.5 Planning Node

```python
# domain/services/graphs/nodes/planning.py
from langchain_core.messages import HumanMessage, SystemMessage
from app.domain.services.graphs.state import AgentState

PLANNING_SYSTEM_PROMPT = """You are a planning agent. Given the user's request,
create a structured plan with concrete steps. Return a JSON object:
{
    "goal": "high-level goal",
    "steps": [
        {"description": "what to do", "context": "why and how"}
    ]
}
Keep plans concise: 2-5 steps for most tasks."""


def make_planning_node(llm):
    """Factory: returns a planning node with llm bound via closure."""

    async def planning_node(state: AgentState) -> dict:
        """Generate a structured plan from the user's request."""
        messages = [
            SystemMessage(content=PLANNING_SYSTEM_PROMPT),
            *state["messages"],
        ]

        response = await llm.ainvoke(messages)
        plan = _parse_plan(response.content)

        return {
            "messages": [response],
            "plan": plan,
            "current_step_index": 0,
            "step_results": [],
        }

    return planning_node


def _parse_plan(content: str) -> dict:
    """Parse LLM plan response into structured dict."""
    import json
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Fallback: treat entire response as a single step
        return {
            "goal": "Execute user request",
            "steps": [{"description": content, "context": ""}],
        }
```

### 4.6 Verification Node

```python
# domain/services/graphs/nodes/verification.py
from langchain_core.messages import HumanMessage, SystemMessage
from app.domain.services.graphs.state import AgentState

VERIFICATION_PROMPT = """Review the executed steps and their results.
Determine if the plan was completed successfully.
If critical issues exist, respond with 'REPLAN: <reason>'.
Otherwise, respond with 'PASSED: <summary>'."""


def make_verification_node(llm):
    """Factory: returns a verification node with llm bound via closure."""

    async def verification_node(state: AgentState) -> dict:
        """Verify execution results and decide pass/replan."""
        step_summary = "\n".join(
            f"Step {r['step_index']}: {r['description']} -> {r['status']}"
            for r in state["step_results"]
        )

        messages = [
            SystemMessage(content=VERIFICATION_PROMPT),
            HumanMessage(content=f"Steps executed:\n{step_summary}"),
        ]

        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    return verification_node
```

### 4.7 Tool Adaptation Layer

```python
# domain/services/tools/langchain_adapters.py
from typing import Any
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model
from app.domain.services.tools.base import BaseTool as PythinkerBaseTool


def adapt_pythinker_tools(pythinker_tools: list[PythinkerBaseTool]) -> list[StructuredTool]:
    """Convert all Pythinker tools to LangChain StructuredTools.

    Each Pythinker tool exposes N functions via get_tools().
    Each function becomes a separate StructuredTool.

    Example: ShellTool.get_tools() returns 5 schemas ->
             5 StructuredTool instances (shell_exec, shell_view, etc.)
    """
    adapted = []
    for pythinker_tool in pythinker_tools:
        for schema in pythinker_tool.get_tools():
            func_def = schema["function"]
            func_name = func_def["name"]

            # Build Pydantic model from JSON schema parameters
            args_model = _json_schema_to_pydantic(func_name, func_def.get("parameters", {}))

            # Create async wrapper that delegates to Pythinker tool
            # ToolResult fields: success (bool), message (str|None), data (Any|None)
            async def _invoke(
                _tool=pythinker_tool, _name=func_name, **kwargs: Any
            ) -> str:
                result = await _tool.invoke_function(_name, **kwargs)
                if result.success:
                    return result.message or "Success (no output)"
                return f"Error: {result.message or 'Unknown error'}"

            adapted.append(
                StructuredTool.from_function(
                    coroutine=_invoke,
                    name=func_name,
                    description=func_def.get("description", ""),
                    args_schema=args_model,
                )
            )
    return adapted


def _json_schema_to_pydantic(name: str, schema: dict) -> type[BaseModel]:
    """Convert OpenAI function parameters JSON schema to a Pydantic model.

    Preserves field descriptions — LangChain uses these to generate the
    tool schema sent to the LLM. Without descriptions, the LLM sees
    parameter names but no explanation, degrading tool-calling accuracy.
    """
    from pydantic import Field as PydanticField

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    fields = {}
    for prop_name, prop_def in properties.items():
        python_type = _json_type_to_python(prop_def.get("type", "string"))
        description = prop_def.get("description", "")
        default = ... if prop_name in required else None
        fields[prop_name] = (python_type, PydanticField(default=default, description=description))

    return create_model(f"{name}_args", **fields)


def _json_type_to_python(json_type: str) -> type:
    """Map JSON schema type to Python type."""
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, str)
```

### 4.8 LLM Provider Integration

```python
# infrastructure/external/llm/langchain_llm.py
import logging
from langchain_openai import ChatOpenAI
from app.core.config_llm import get_llm_settings

logger = logging.getLogger(__name__)


class RotatingChatOpenAI:
    """ChatOpenAI wrapper with API key rotation on 429/401 errors.

    Replaces the APIKeyPool pattern. Maintains a list of API keys and
    creates a new ChatOpenAI instance when the current key fails.

    All Pythinker providers (GLM, DeepSeek, Kimi, OpenRouter)
    are OpenAI-compatible. ChatOpenAI handles them via base_url.
    """

    def __init__(self):
        settings = get_llm_settings()
        self._api_keys = settings.get_all_api_keys()  # Returns list of keys
        self._current_key_index = 0
        self._settings = settings
        self._model: ChatOpenAI | None = None

    def get_model(self) -> ChatOpenAI:
        """Get current ChatOpenAI instance, creating if needed."""
        if self._model is None:
            self._model = self._create_model(self._api_keys[self._current_key_index])
        return self._model

    def rotate_key(self) -> ChatOpenAI:
        """Rotate to next API key and return new model instance.

        Called by error handler when 429/401 is detected.
        """
        self._current_key_index = (self._current_key_index + 1) % len(self._api_keys)
        logger.warning(f"Rotating API key to index {self._current_key_index}")
        self._model = self._create_model(self._api_keys[self._current_key_index])
        return self._model

    def _create_model(self, api_key: str) -> ChatOpenAI:
        return ChatOpenAI(
            model=self._settings.model_name,
            openai_api_key=api_key,
            openai_api_base=self._settings.api_base,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
            streaming=True,
        )


# Singleton
_rotating_llm: RotatingChatOpenAI | None = None


def get_chat_model() -> ChatOpenAI:
    """Get the current ChatOpenAI instance with key rotation support."""
    global _rotating_llm
    if _rotating_llm is None:
        _rotating_llm = RotatingChatOpenAI()
    return _rotating_llm.get_model()


def rotate_and_get_chat_model() -> ChatOpenAI:
    """Rotate API key and return new model. Called on 429/401."""
    global _rotating_llm
    if _rotating_llm is None:
        _rotating_llm = RotatingChatOpenAI()
    return _rotating_llm.rotate_key()
```

**Key rotation integration**: Since `create_react_agent(model=llm)` captures the model at
build time, a rotated model won't automatically propagate into compiled subgraphs. Two options:

1. **Rebuild on rotation** (simpler): The graph is not compiled once globally — it is built
   per-session in `agent_service.py`. If a session hits 429 mid-execution, the error handler
   rotates the key, and the next graph invocation (retry or new session) uses the new model.
   Within a single graph run, the ReAct agent retries with the same key (LangChain's built-in
   retry handles transient 429s with backoff).

2. **Model proxy** (more complex, if needed): Wrap `ChatOpenAI` in a thin proxy that delegates
   to `RotatingChatOpenAI.get_model()` on every call, so the underlying model swaps transparently.
   This requires implementing `BaseChatModel` interface methods to proxy calls.

Recommended: **Option 1** for initial migration. Option 2 if rotation frequency is high.

### 4.9 MongoDB Checkpointer

```python
# domain/services/graphs/checkpointer.py
from langgraph.checkpoint.mongodb.aio import AsyncMongoDBSaver
from app.core.config import get_settings

_checkpointer: AsyncMongoDBSaver | None = None


async def get_checkpointer() -> AsyncMongoDBSaver:
    """Get or create MongoDB checkpointer singleton.

    Saves state after every graph node execution.
    Enables: crash recovery, HITL pause/resume, time-travel debugging.

    Uses a separate database to avoid polluting the main pythinker DB.
    TTL index recommended on checkpoints collection (7-day expiry).
    """
    global _checkpointer
    if _checkpointer is None:
        settings = get_settings()
        _checkpointer = AsyncMongoDBSaver.from_conn_string(
            settings.mongodb_url,
            db_name="pythinker_checkpoints",
        )
        # Required: creates indexes and verifies connection
        await _checkpointer.setup()
    return _checkpointer


async def shutdown_checkpointer() -> None:
    """Cleanup checkpointer on app shutdown."""
    global _checkpointer
    if _checkpointer is not None:
        # AsyncMongoDBSaver uses motor; close the underlying client
        _checkpointer = None
```

**Lifecycle integration** — wire into FastAPI lifespan:

```python
# In main.py lifespan
from app.domain.services.graphs.checkpointer import get_checkpointer, shutdown_checkpointer

@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_checkpointer()  # Initialize + setup on startup
    yield
    await shutdown_checkpointer()  # Cleanup on shutdown
```

### 4.10 SSE Event Mapper

```python
# application/services/event_mapper.py
import asyncio
import time
from collections.abc import AsyncGenerator
from app.domain.models.event import (
    BaseEvent, DoneEvent, ErrorEvent, MessageEvent, PlanEvent, PlanningPhase,
    PlanStatus, ProgressEvent, StepEvent, StepStatus, StreamEvent, ToolEvent, ToolStatus,
)
from app.domain.models.plan import Plan, Step, StepType


async def stream_graph_as_pythinker_events(
    graph, input_state: dict | None, config: dict
) -> AsyncGenerator[BaseEvent, None]:
    """Bridge LangGraph astream_events to Pythinker SSE events.

    Maps LangGraph's internal event stream to the existing frontend
    SSE contract so the Vue app requires zero changes.

    LangGraph v2 events -> Pythinker events:
      on_chat_model_stream  -> StreamEvent (token-level)
      on_tool_start         -> ToolEvent(status=CALLING, tool_call_id, function_name, function_args)
      on_tool_end           -> ToolEvent(status=CALLED, function_result)
      on_chain_start        -> StepEvent(status=STARTED, step=Step)
      on_chain_end          -> StepEvent(status=COMPLETED) / MessageEvent / DoneEvent

    Note: input_state is None for checkpoint resume (crash recovery).
    When None, LangGraph resumes from the last checkpoint for the thread_id.
    """
    last_heartbeat = time.monotonic()
    HEARTBEAT_INTERVAL = 30  # seconds — prevents proxy timeouts

    try:
        async for event in graph.astream_events(input_state, config, version="v2"):
            kind = event["event"]
            data = event.get("data", {})
            name = event.get("name", "")
            run_id = event.get("run_id", "")

            # --- Token streaming ---
            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield StreamEvent(content=chunk.content)

            # --- Tool start ---
            elif kind == "on_tool_start":
                tool_input = data.get("input", {})
                yield ToolEvent(
                    tool_call_id=run_id,
                    tool_name=name,
                    function_name=name,
                    function_args=tool_input if isinstance(tool_input, dict) else {"input": str(tool_input)},
                    status=ToolStatus.CALLING,
                )

            # --- Tool end ---
            elif kind == "on_tool_end":
                yield ToolEvent(
                    tool_call_id=run_id,
                    tool_name=name,
                    function_name=name,
                    function_args={},
                    status=ToolStatus.CALLED,
                    function_result=str(data.get("output", "")),
                )

            # --- Step start ---
            elif kind == "on_chain_start" and name == "execute_step":
                # Construct a minimal Step object for the frontend
                yield StepEvent(
                    step=Step(description="Executing step", step_type=StepType.EXECUTION),
                    status=StepStatus.STARTED,
                )

            # --- Step end ---
            elif kind == "on_chain_end" and name == "execute_step":
                yield StepEvent(
                    step=Step(description="Step completed", step_type=StepType.EXECUTION),
                    status=StepStatus.COMPLETED,
                )

            # --- Summarization complete ---
            elif kind == "on_chain_end" and name == "summarize":
                output = data.get("output", {})
                if isinstance(output, dict) and "final_report" in output:
                    yield MessageEvent(message=output["final_report"])

            # --- Heartbeat (prevents proxy/SSE timeout) ---
            now = time.monotonic()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield ProgressEvent(
                    phase=PlanningPhase.HEARTBEAT,
                    message="Processing...",
                )
                last_heartbeat = now

        yield DoneEvent()

    except Exception as e:
        yield ErrorEvent(
            error=str(e),
            error_type="graph_execution",
            recoverable=True,
        )
```

**Key design decisions:**
- `tool_call_id` uses LangGraph's `run_id` which uniquely identifies each tool invocation
- `function_name` and `tool_name` both use the tool `name` (LangGraph does not distinguish these)
- `function_args` comes from `data["input"]` on tool start
- `Step` objects are constructed minimally — the frontend only needs `description` and `type` for rendering
- `input_state=None` triggers checkpoint resume (crash recovery) — no new input, graph resumes from last node
- Heartbeat `ProgressEvent` every 30s prevents proxy timeouts (matching existing behavior)

### 4.11 PlanEvent Emission

The existing frontend expects `PlanEvent` with a `Plan` Pydantic model to render the plan panel.
Since the graph stores `plan` as a plain `dict`, the planning node must emit a `PlanEvent` through
the event mapper when the plan is created:

```python
# In the event mapper, handle planning node completion:
elif kind == "on_chain_end" and name == "plan":
    output = data.get("output", {})
    plan_dict = output.get("plan")
    if plan_dict:
        # Convert plain dict to Plan Pydantic model for frontend compatibility.
        # Strip unknown fields (e.g. "context" from LLM) before validation,
        # since Step model does not allow extras.
        clean_steps = [
            {k: v for k, v in s.items() if k in Step.model_fields}
            for s in plan_dict.get("steps", [])
        ]
        plan_model = Plan.model_validate({**plan_dict, "steps": clean_steps})
        yield PlanEvent(plan=plan_model, status=PlanStatus.CREATED)
```

If `Plan.from_dict()` is too heavy, a lightweight alternative is to emit a new `PlanDictEvent`
type that the frontend accepts. But reusing the existing `PlanEvent` + `Plan` model is simpler
since the frontend already renders it.

### 4.12 Dynamic Tool Selection

The existing system uses `DynamicToolsetManager` to select relevant tools per task, avoiding
context window waste from registering all 50+ tool functions for every LLM call.

In the LangGraph migration, this is handled by:

1. **Per-node tool scoping**: Each node factory (`make_execution_node`, `make_planning_node`)
   receives only the tools relevant to its phase. The graph builder selects tools per node:

```python
# In agent_graph.py
planning_tools = [search_tool]  # Planning only needs search
execution_tools = adapt_pythinker_tools([shell, browser, file, search, ...])  # Full set
verify_tools = []  # Verification is LLM-only

workflow.add_node("plan", make_planning_node(llm))  # No tools
workflow.add_node("execute_step", make_execution_node(llm, execution_tools))
workflow.add_node("verify", make_verification_node(llm))  # No tools
```

2. **Optional dynamic filtering**: For complex tasks, a routing function can inspect the plan
   step type and select a subset of tools before passing to `create_react_agent`. This replaces
   `BaseAgent.PHASE_TOOL_GROUPS`.

### 4.13 Deletion Inventory — Complete Accounting

The `domain/services/agents/` directory contains ~80 files. The following categorizes ALL files:

**Deleted (replaced by LangGraph):**
All files listed in Section 3 "What gets deleted" (~50 files).

**Also deleted (not previously listed but superseded):**
- `agent_context.py`, `agent_context_factory.py` — context assembly (LangGraph manages state)
- `parallel_executor.py` — parallel step execution (LangGraph handles via subgraphs)
- `research_agent.py` — research-specific agent (becomes a graph node or tool)
- `task_decomposer.py` — task decomposition (absorbed into planning node)
- `spawner.py` — agent spawning (replaced by subgraph composition)
- `guardrails.py`, `content_safety.py`, `compliance_gates.py` — safety checks (dropped per user decision)
- `self_healing_loop.py` — auto-recovery (LangGraph checkpointing replaces this)
- `gaming_detector.py` — abuse detection (dropped per user decision)

**Kept (utility files not tied to agent orchestration):**
- `agent_session_lifecycle.py` — sandbox lifecycle management (still needed)
- `agent_task_factory.py` — sandbox allocation (simplified but kept)
- Any files that are pure utility functions without agent orchestration logic

**Rule**: If a file's primary purpose is agent orchestration, state management, or reliability
monitoring, it gets deleted. If it manages sandbox lifecycle or external resource allocation,
it stays and gets simplified.

## 5. Data Flow

### 5.1 Request to Response

```
POST /sessions/{id}/chat
  │
  ├── AgentService.chat()
  │     Builds input state: {messages, session_id, sandbox_id, mode, ...}
  │     Config: {"configurable": {"thread_id": session_id}}
  │
  ├── stream_graph_as_pythinker_events(graph, input, config)
  │     │
  │     ├── graph.astream_events() internally:
  │     │     route → plan → execute_step ←→ execute_step → verify → summarize
  │     │     (checkpointed after every node)
  │     │
  │     ├── Maps each LangGraph event to Pythinker event type
  │     └── Yields: StreamEvent, ToolEvent, StepEvent, MessageEvent, DoneEvent
  │
  └── EventSourceResponse streams events to frontend via SSE
```

### 5.2 Crash Recovery

```
Process crashes during execute_step (step 3 of 5)
  │
  ├── MongoDB checkpoint has state after step 2 (last completed node)
  │
  ├── User reconnects, POST /sessions/{id}/chat
  │     Same thread_id in config
  │
  ├── AgentService detects existing checkpoint for thread_id:
  │     checkpoint = await graph.aget_state(config)
  │     if checkpoint.values:  # Existing state found
  │         # Resume: pass None as input (no new user message)
  │         stream = graph.astream_events(None, config, version="v2")
  │     else:
  │         # Fresh run: pass full input state
  │         stream = graph.astream_events(input_state, config, version="v2")
  │
  ├── Graph resumes from execute_step (step 3)
  │
  └── Frontend receives events from step 3 onward
```

**Key distinction**: `input=None` triggers checkpoint resume. `input={...}` starts a fresh run.
The `agent_service.py` must check for existing checkpoints to decide which path to take.

### 5.3 Tool Execution (inside ReAct agent)

```
ReAct agent loop (inside execute_step node):
  │
  ├── LLM call → returns tool_calls: [{name: "shell_exec", args: {cmd: "ls"}}]
  │
  ├── LangGraph dispatches to StructuredTool("shell_exec")
  │     └── Adapter calls PythinkerShellTool.invoke_function("shell_exec", cmd="ls")
  │           └── HTTP to sandbox container → shell execution → ToolResult
  │
  ├── Tool result appended to messages (role: "tool")
  │
  ├── LLM call → next action or final response
  │
  └── Loop ends when LLM returns no tool_calls
```

## 6. Dependencies

### New dependencies

```
# requirements.txt additions
langgraph>=1.0.10,<2.0.0
langchain-core>=0.3.0,<0.4.0
langchain-openai>=0.3.0,<0.4.0
langgraph-checkpoint-mongodb>=0.1.0,<1.0.0
```

### Removed dependencies

```
# requirements.txt removals
instructor    # Replaced by LangChain structured output
# tenacity    # Keep if used outside agent stack
```

### Version pinning strategy

Pin upper bounds to avoid LangGraph 2.0 breaking changes (expected Q2 2026). Migrate to 2.0 explicitly when stable.

## 7. Migration Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| GLM JSON quirks lost | High | Custom `ChatOpenAI` subclass overriding `_agenerate()` with JSON repair, or LangChain output parser with retry |
| API key pool rotation lost | Medium | Custom LangChain callback handler that catches 429/401, rotates keys, retries |
| LangGraph 2.0 breaking changes | Medium | Pin `langgraph<2.0.0`; dedicate migration sprint when 2.0 stabilizes |
| `langchain-core` dependency weight | Low | ~50MB added to image; acceptable |
| Frontend SSE contract break | Low | Event mapper preserves exact same event types; no frontend changes |
| Checkpoint storage growth | Low | MongoDB TTL index on checkpoints collection; 7-day auto-expiry |
| Provider-specific structured output | Medium | LangChain's `with_structured_output()` handles most cases; test with each provider |
| Sandbox tool latency unchanged | None | Tool implementations untouched; only the dispatch layer changes |
| Prometheus metrics lost | Low | Existing metrics (`pythinker_tool_errors_total`, `pythinker_step_failures_total`, `pythinker_model_tier_selections_total`) are dropped with the old agent stack. Re-add as LangGraph callback handlers that increment counters on `on_tool_end` (error check), `on_chain_end` (step completion), etc. This is Phase 2+ work, not blocking. |

## 8. Testing Strategy

### Unit tests
- Graph compilation: verify `build_agent_graph()` compiles without errors
- Routing functions: test `mode_router`, `step_router`, `verify_router` with mock states
- Tool adapters: test `adapt_pythinker_tools()` produces correct StructuredTool schemas
- Event mapper: test each LangGraph event type maps to correct Pythinker event

### Integration tests
- Full graph run with mock LLM (LangChain `FakeListChatModel`)
- Checkpoint save/restore: run graph, kill mid-step, resume, verify correct state
- SSE streaming: verify frontend receives expected event sequence

### E2E tests
- Run full agent workflow against real sandbox with real LLM
- Verify tool execution works through adapter layer
- Verify SSE stream delivers correct events to frontend

### Deleted test updates
- Remove all tests for deleted files (base.py, execution.py, planner.py, etc.)
- Remove middleware pipeline tests
- Remove monitor/detector tests
- Remove LLM implementation tests (openai_llm.py, etc.)

## 9. Migration Approach

### Phase 1: Foundation (parallel, no deletions)
1. Add LangGraph dependencies
2. Create `domain/services/graphs/` directory structure
3. Implement `state.py`, `checkpointer.py`, `langchain_llm.py`
4. Implement `langchain_adapters.py` — tool wrapper layer
5. Write and pass unit tests for all new components

### Phase 2: Graph implementation (parallel, no deletions)
1. Implement all nodes: planning, execution, verification, summarization, discuss, fast_search
2. Implement routing functions
3. Build `agent_graph.py`
4. Implement `event_mapper.py`
5. Write and pass integration tests with mock LLM

### Phase 3: Wiring (modify existing files)
1. Update `agent_service.py` to use graph instead of old flows
2. Update `session_routes.py` SSE endpoint to use event mapper
3. Simplify `agent_domain_service.py`
4. Run E2E tests against real sandbox

### Phase 4: Cleanup (delete old files)
1. Delete all files listed in Section 3 "What gets deleted"
2. Remove unused imports and dead code across remaining files
3. Remove old dependencies from requirements.txt
4. Update all remaining tests
5. Final lint + type-check pass

### Phase ordering rationale
Phases 1-2 add new code alongside old code (no risk). Phase 3 is the switchover (can be reverted by pointing back to old code). Phase 4 is cleanup after Phase 3 is validated. At no point is the system in a broken state.

## 10. Success Criteria

- [ ] Agent stack reduced from ~50 files / ~15,000 lines to ~15 files / ~1,500 lines
- [ ] All existing tool types work through adapter layer (shell, browser, file, search, etc.)
- [ ] SSE streaming to frontend works identically (no frontend changes)
- [ ] MongoDB checkpointing enabled; crash recovery verified
- [ ] All three flows work: agent (plan→execute→verify), discuss, fast_search
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `pytest tests/` pass (with updated test suite)
- [ ] Full E2E workflow completes against real sandbox
