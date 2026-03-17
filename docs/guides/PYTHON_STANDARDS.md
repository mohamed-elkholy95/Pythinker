# Python Backend Coding Standards

This document defines mandatory coding standards for all Python backend code based on Pydantic v2, FastAPI, Legacy Flow, and Python 3.11+ async patterns.

## Pydantic v2 Best Practices

### ConfigDict for Model Configuration

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class AgentResponse(BaseModel):
    """Always use ConfigDict for model configuration"""
    model_config = ConfigDict(
        strict=True,           # No type coercion - prevents LLM confusion
        frozen=True,           # Immutable instances
        extra='forbid',        # No extra fields allowed
        validate_assignment=True,  # Validate on attribute assignment
    )

    thinking: str = Field(..., min_length=1, max_length=5000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)
    hallucination_risk: float = Field(default=0.0, ge=0.0, le=1.0)

# ✅ Strict mode rejects type coercion
# AgentResponse(thinking="test", confidence="0.8")  # Fails in strict mode
```

### Field Validators Must Be Classmethods (Pydantic v2)

```python
from pydantic import BaseModel, field_validator, model_validator

class AgentThought(BaseModel):
    observations: str
    analysis: str

    # ✅ CRITICAL: @field_validator MUST be @classmethod in Pydantic v2
    @field_validator("observations", "analysis")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    # ✅ Model-level validation
    @model_validator(mode="after")
    def validate_consistency(self) -> "AgentThought":
        if len(self.analysis) < len(self.observations):
            raise ValueError("Analysis should be at least as detailed as observations")
        return self
```

### ORM/Database Integration

```python
from pydantic import BaseModel, ConfigDict

class SessionFromDB(BaseModel):
    """Load from Beanie/MongoDB documents"""
    model_config = ConfigDict(
        from_attributes=True,  # Allow loading from ORM objects
        populate_by_name=True,  # Accept both alias and field name
    )

    id: str
    user_id: str
    created_at: datetime

# Usage with Beanie
db_session = await AgentSession.find_one({"session_id": sid})
validated = SessionFromDB.model_validate(db_session)
```

## Python 3.11+ Async Patterns

### TaskGroup for Concurrent Operations (NOT asyncio.gather)

```python
import asyncio

async def execute_tools_concurrently(tool_calls: list[ToolCall]) -> dict:
    """
    Use TaskGroup instead of asyncio.gather():
    - Captures ALL exceptions (gather fails on first)
    - Provides exception groups for handling different error types
    - Cleaner exception handling with except* syntax
    """
    results = {}
    errors = {}

    async def execute_single(tool_call: ToolCall) -> tuple[str, Any]:
        result = await tool_registry[tool_call.tool_name](**tool_call.parameters)
        return tool_call.tool_name, result

    try:
        async with asyncio.TaskGroup() as tg:
            tasks = {
                tc.tool_name: tg.create_task(execute_single(tc))
                for tc in tool_calls
            }
    except* ValueError as ve:
        # Handle validation errors specifically
        for exc in ve.exceptions:
            errors["validation"] = str(exc)
    except* TimeoutError as te:
        # Handle timeouts specifically
        for exc in te.exceptions:
            errors["timeout"] = str(exc)
    except* Exception as eg:
        # Catch all other exceptions
        for exc in eg.exceptions:
            errors["general"] = str(exc)

    # Collect results from completed tasks
    for name, task in tasks.items():
        try:
            _, result = task.result()
            results[name] = result
        except Exception as e:
            errors[name] = str(e)

    return {"results": results, "errors": errors}
```

### Async Context Managers for Resource Management

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator

@asynccontextmanager
async def managed_browser_session() -> AsyncGenerator[Browser, None]:
    """
    Async context manager ensures cleanup even on exceptions.
    CRITICAL for browser/database connections.
    """
    browser = Browser(config=BrowserConfig(headless=True))
    try:
        yield browser
    finally:
        await browser.close()

# Usage
async def web_research(query: str) -> str:
    async with managed_browser_session() as browser:
        agent = BrowserAgent(task=query, browser=browser)
        result = await agent.run()
        return result.final_result()
```

## FastAPI Dependency Injection

### Yield Dependencies with Proper Exception Handling (FastAPI 0.110.0+)

```python
from fastapi import Depends, HTTPException
from typing import Annotated

async def get_database_session():
    """
    CRITICAL: FastAPI 0.110.0+ requires re-raising exceptions
    in yield dependencies to prevent memory leaks.
    """
    session = await create_session()
    try:
        yield session
    except HTTPException:
        await session.rollback()
        raise  # MUST re-raise
    except Exception as e:
        await session.rollback()
        raise  # MUST re-raise
    finally:
        await session.close()

# ❌ BAD - causes memory leaks in FastAPI 0.110.0+
async def bad_dependency():
    try:
        yield resource
    except SomeException:
        pass  # Swallowing exception causes memory leak

# ✅ GOOD - always re-raise
async def good_dependency():
    try:
        yield resource
    except SomeException:
        raise  # Must re-raise

# Usage with Annotated (recommended)
@app.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_database_session)]
):
    return await db.get(session_id)
```

## Legacy Flow Patterns

### StateGraph with TypedDict and Checkpointing

```python
from legacy-flow.graph import StateGraph, START, END
from legacy-flow.checkpoint.memory import InMemorySaver
from legacy-flow.types import Command
from typing import TypedDict, Annotated, Literal
from operator import add

class AgentState(TypedDict):
    """State must use TypedDict with Annotated for list accumulation"""
    user_query: str
    session_id: str
    research_findings: Annotated[list[str], add]  # Accumulates across nodes
    thought_process: list[dict]
    final_response: str
    hallucination_risk: float

def thinking_node(state: AgentState) -> dict:
    """Nodes return partial state updates"""
    thought = analyze_query(state["user_query"])
    return {"thought_process": [thought]}

def research_node(state: AgentState) -> dict:
    """Research findings accumulate via Annotated[list, add]"""
    findings = search_web(state["user_query"])
    return {"research_findings": findings}

# Command for combined state update + routing (Legacy Flow best practice)
def routing_node(state: AgentState) -> Command[Literal["research", "generate"]]:
    """Use Command to update state AND route in one step"""
    if needs_research(state):
        return Command(
            update={"thought_process": [{"decision": "needs_research"}]},
            goto="research"
        )
    return Command(
        update={"thought_process": [{"decision": "ready_to_generate"}]},
        goto="generate"
    )

# Build graph
builder = StateGraph(AgentState)
builder.add_node("think", thinking_node)
builder.add_node("route", routing_node)
builder.add_node("research", research_node)
builder.add_node("generate", generate_node)

builder.add_edge(START, "think")
builder.add_edge("think", "route")
# Routing handled by Command in routing_node
builder.add_edge("research", "generate")
builder.add_edge("generate", END)

# Compile with checkpointing for persistence
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# Invoke with thread_id for state persistence
config = {"configurable": {"thread_id": session_id}}
result = graph.invoke(initial_state, config)
```

## Structured Logging with structlog

### Production Configuration

```python
import structlog
import logging
from structlog.contextvars import bind_contextvars, clear_contextvars

# Production-ready configuration
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # Merge context variables
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),  # JSON for log aggregation
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Bind context for request tracing
async def process_request(request_id: str, session_id: str):
    bind_contextvars(request_id=request_id, session_id=session_id)

    logger.info("agent_started", action="research")
    # All subsequent logs include request_id and session_id

    clear_contextvars()  # Clean up after request
```

## Retry Strategy with Tenacity

### Combining Tenacity with Pydantic Validation

```python
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    before_sleep_log
)
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((ValidationError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
async def generate_verified_response(prompt: str) -> AgentResponse:
    """
    LLM call with:
    1. Exponential backoff (2s, 4s, 8s)
    2. Retry on Pydantic validation errors (forces LLM to fix output)
    3. Retry on timeouts
    """
    raw_response = await llm.invoke(prompt)
    # Pydantic validates - raises ValidationError if invalid
    return AgentResponse.model_validate_json(raw_response)
```

## AI Agent Anti-Hallucination Patterns

### Critic-Verifier Loop (Never Trust Raw LLM Output)

```python
async def verified_agent_response(query: str) -> AgentResponse:
    """
    3-layer defense against hallucinations:
    1. Generate with citations required
    2. Verify citations exist
    3. Grade relevance before returning
    """
    # Layer 1: Generate with citation requirement
    response = await llm.invoke(f"""
    Answer based ONLY on provided context.
    Every factual claim MUST end with [source_id].
    If not in context, say "I do not have information."

    Query: {query}
    """)

    # Layer 2: Verify citations
    parsed = AgentResponse.model_validate_json(response)
    if not parsed.citations:
        parsed.hallucination_risk = 0.9  # Flag as likely hallucination

    # Layer 3: Grade relevance
    for citation in parsed.citations:
        if not await verify_source_exists(citation):
            parsed.hallucination_risk = max(parsed.hallucination_risk, 0.7)

    return parsed
```

## Production Checklist

Before committing Python backend code:
- [ ] All Pydantic models use `ConfigDict(strict=True)` where appropriate
- [ ] All `@field_validator` methods are `@classmethod`
- [ ] `asyncio.TaskGroup` used instead of `asyncio.gather` for concurrent operations
- [ ] FastAPI yield dependencies re-raise exceptions (0.110.0+ requirement)
- [ ] Legacy Flow state uses `TypedDict` with `Annotated[list, add]` for accumulation
- [ ] structlog configured with JSON output and context variables
- [ ] Tenacity retry wraps LLM calls with Pydantic validation
- [ ] No raw LLM output sent to users without verification
