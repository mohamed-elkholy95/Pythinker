# Comprehensive Plan: Qdrant Vector Database Integration for Pythinker

**Date**: 2026-02-07
**Status**: Draft — Pending Approval
**Reference**: Manus AI Vector Database Implementation (Milvus/Zilliz Architecture)

---

## 1. Executive Summary

Pythinker already has significant Qdrant infrastructure scaffolded but **not wired up or actively used**. This plan bridges the gap between the existing scaffolding and a full Manus-style "Memory OS" architecture, converting Pythinker's vector database from dormant infrastructure into an active, hierarchical memory system that enables cross-session learning, semantic retrieval, and role-scoped agent context.

### Current State vs Target State

| Aspect | Current State | Target State |
|--------|--------------|--------------|
| **Qdrant connectivity** | Initializes at startup, health-checked | Same (already done) |
| **Domain port wiring** | `set_vector_memory_repository()` never called | Called at startup, QdrantMemoryRepository connected |
| **Collections** | 1 (`agent_memories`) + 1 dormant (`semantic_cache`) | 4 active collections (see §3) |
| **Memory extraction** | Service exists, never called during sessions | Auto-extracts after every session |
| **Agent context injection** | Partial (execution.py, planner.py) | Full: planning, execution, reflection |
| **Role-scoped retrieval** | None | Per-agent memory lens filters |
| **Cross-session learning** | None | Task outcomes, error patterns, user prefs |
| **Semantic cache** | Built but disabled (`semantic_cache_enabled=False`) | Enabled with feature flag |
| **Feature flags** | `feature_parallel_memory=False` | Enabled, tested |

---

## 2. Audit of Existing Infrastructure

### 2.1 What's Already Built (Reuse As-Is)

| Component | File | Status |
|-----------|------|--------|
| Qdrant client singleton | `infrastructure/storage/qdrant.py` | Working, initializes at startup |
| Qdrant CRUD + search | `infrastructure/repositories/qdrant_memory_repository.py` | Complete, 267 LOC |
| Domain port (VectorMemoryRepository) | `domain/repositories/vector_memory_repository.py` | Abstract interface defined |
| Memory models (8 types) | `domain/models/long_term_memory.py` | Complete with dedup, lifecycle |
| Memory repository interface | `domain/repositories/memory_repository.py` | Full CRUD + search contract |
| MemoryService | `domain/services/memory_service.py` | Hybrid search (Qdrant→Mongo→keyword) |
| Embedding generation | `memory_service.py:879-958` | OpenAI text-embedding-3-small (1536-dim) |
| Extraction pipeline | `memory_service.py:548-665` | Pattern + LLM extraction |
| Context engineering | `memory_service.py:1096-1383` | In-session summarization |
| Semantic cache | `infrastructure/external/cache/semantic_cache.py` | Qdrant + Redis, disabled |
| Error pattern analyzer | `agents/error_pattern_analyzer.py` | Persist/load via MemoryService |
| Migration script | `scripts/migrate_to_qdrant.py` | Batch migration utility |
| Docker Qdrant service | `docker-compose.yml` | Ports 6333/6334, health checks |
| Config | `core/config.py:72-76` | URL, gRPC, collection, API key |
| .env | `.env:128-132` | QDRANT_URL, GRPC_PORT, COLLECTION |

### 2.2 What's Broken / Missing Wiring

| Issue | Location | Fix |
|-------|----------|-----|
| `QdrantMemoryRepository` doesn't extend `VectorMemoryRepository` | `qdrant_memory_repository.py` | Add ABC inheritance |
| `set_vector_memory_repository()` never called | `main.py` | Wire at startup after Qdrant init |
| `MemoryService` not injected into agent task runner | `agent_task_runner.py` | Create & inject during session init |
| `extract_from_conversation()` never called | Session lifecycle | Call on session end |
| `extract_from_task_result()` never called | Agent completion flow | Call when task completes |
| `feature_parallel_memory` always False | `.env` + config | Enable after wiring verified |
| `semantic_cache_enabled` always False | `.env` + config | Enable after dependencies ready |
| `get_embedding_client()` referenced in semantic_cache but doesn't exist | `infrastructure/external/embedding/` | Create embedding client module |

---

## 3. Multi-Collection Architecture (Manus-Aligned)

### 3.1 Collection Schema

Aligning with Manus's 4-collection pattern, using Qdrant's payload indexing:

#### Collection 1: `user_knowledge` (NEW)
User-provided documents, preferences, project context.

```python
VectorParams(size=1536, distance=Distance.COSINE)
# Payload schema:
{
    "user_id": str,           # Indexed — partition key
    "memory_type": str,       # Indexed — PREFERENCE, FACT, ENTITY, PROJECT_CONTEXT
    "importance": str,        # Indexed — critical, high, medium, low
    "tags": list[str],        # Indexed — for tag-based filtering
    "created_at": float,      # Indexed — timestamp for recency
    "access_count": int,      # For LRU-like retrieval
    "session_id": str | None, # Source session
    "content_hash": str,      # Dedup key
}
```

#### Collection 2: `task_artifacts` (NEW)
Intermediate outputs, plans, code snippets from task execution.

```python
VectorParams(size=1536, distance=Distance.COSINE)
# Payload schema:
{
    "user_id": str,           # Indexed
    "session_id": str,        # Indexed — which session
    "task_id": str | None,    # Task identifier
    "artifact_type": str,     # Indexed — TASK_OUTCOME, PROCEDURE, CONVERSATION
    "agent_role": str,        # Indexed — planner, executor, researcher
    "step_index": int | None, # Step within workflow
    "success": bool | None,   # Outcome indicator
    "created_at": float,      # Indexed
}
```

#### Collection 3: `tool_logs` (NEW)
Success/failure patterns from tool executions — enables learning from past tool use.

```python
VectorParams(size=1536, distance=Distance.COSINE)
# Payload schema:
{
    "user_id": str,           # Indexed
    "session_id": str,        # Indexed
    "tool_name": str,         # Indexed — shell_exec, browser_navigate, etc.
    "input_hash": str,        # Indexed — hash of tool input for dedup
    "outcome": str,           # Indexed — success, failure, timeout
    "error_type": str | None, # Error classification
    "created_at": float,      # Indexed
}
```

#### Collection 4: `reasoning_paths` (NEW — Phase 2)
Embeddings of chain-of-thought and planning steps — enables learning what reasoning worked.

```python
VectorParams(size=1536, distance=Distance.COSINE)
# Payload schema:
{
    "user_id": str,           # Indexed
    "session_id": str,        # Indexed
    "plan_id": str,           # Indexed — which plan
    "node_id": str,           # Step within reasoning
    "parent_node": str | None,# Parent reasoning step
    "reasoning_type": str,    # Indexed — plan, verification, reflection
    "outcome": str | None,    # Whether this reasoning path succeeded
    "created_at": float,      # Indexed
}
```

**Migration Strategy**: The existing `agent_memories` collection maps to `user_knowledge`. We'll keep `agent_memories` as an alias/redirect during migration, then deprecate.

### 3.2 Existing Collection (Keep)

#### `semantic_cache` (existing, dormant → enable)
Already built in `semantic_cache.py`. Enable via `SEMANTIC_CACHE_ENABLED=true`.

---

## 4. Implementation Phases

### Phase 1: Wire Existing Infrastructure (Priority: CRITICAL)
**Effort**: Small — mostly plumbing, no new logic
**Risk**: Low — all components exist, just need connection

#### 1.1 Fix QdrantMemoryRepository ABC compliance
**File**: `backend/app/infrastructure/repositories/qdrant_memory_repository.py`

- Add `VectorMemoryRepository` as base class
- Verify method signatures match the abstract interface
- The existing methods already match — just needs the import + inheritance declaration

#### 1.2 Wire vector repo at startup
**File**: `backend/app/main.py`

After `await get_qdrant().initialize()` succeeds, add:
```python
from app.domain.repositories.vector_memory_repository import set_vector_memory_repository
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository

# Connect Qdrant to domain layer
qdrant_repo = QdrantMemoryRepository()
set_vector_memory_repository(qdrant_repo)
logger.info("Vector memory repository connected to Qdrant")
```

Wrap in the existing try/except so Qdrant failure is graceful.

#### 1.3 Create embedding client module
**File**: `backend/app/infrastructure/external/embedding/client.py` (NEW)

The `semantic_cache.py` references `get_embedding_client()` which doesn't exist. Create it:
```python
class EmbeddingClient:
    """Wrapper around OpenAI embedding API."""
    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

def get_embedding_client() -> EmbeddingClient: ...
```

This wraps the same OpenAI API already used in `memory_service._generate_embedding()` — deduplicate by extracting the shared logic.

#### 1.4 Inject MemoryService into agent lifecycle
**File**: `backend/app/domain/services/agent_task_runner.py`

During session initialization, create and inject MemoryService:
```python
# In _create_task() or run()
from app.domain.services.memory_service import MemoryService
memory_service = MemoryService(repository=mongo_memory_repo, llm=llm)
```

Pass to ExecutionAgent and PlannerAgent constructors (they already accept `memory_service` param).

#### 1.5 Enable feature flags
**File**: `.env`

```bash
FEATURE_PARALLEL_MEMORY=true
# SEMANTIC_CACHE_ENABLED=true  # Enable after Phase 1 verified
```

---

### Phase 2: Memory Extraction Pipeline (Priority: HIGH)
**Effort**: Medium — uses existing extraction methods, adds lifecycle hooks
**Risk**: Low — non-blocking, async, failure-tolerant

#### 2.1 Post-session memory extraction
**File**: `backend/app/domain/services/agent_domain_service.py`

After a session completes (or fails), extract and store memories:

```python
async def _extract_session_memories(self, session, user_id: str):
    """Extract memories from completed session."""
    # 1. Extract from conversation messages
    conversation = [{"role": m.role, "content": m.content} for m in session.messages]
    extracted = await memory_service.extract_from_conversation(user_id, conversation, session.id)

    # 2. Extract task outcome
    if session.task_description and session.final_result:
        task_memories = await memory_service.extract_from_task_result(
            user_id, session.task_description, session.final_result,
            success=(session.status == SessionStatus.COMPLETED),
            session_id=session.id,
        )
        extracted.extend(task_memories)

    # 3. Store all extracted memories (with embeddings + Qdrant sync)
    if extracted:
        await memory_service.store_many(user_id, extracted, session_id=session.id)
```

Call this in `chat()` after the session reaches terminal state (COMPLETED or FAILED).

#### 2.2 Error pattern persistence
**File**: `backend/app/domain/services/agents/error_integration.py`

The `ErrorIntegrationService` already has `on_session_end()` and `persist_patterns()` — ensure these are actually called. Currently the infrastructure exists but the call site may not always execute.

#### 2.3 Tool execution logging to vector DB
**File**: `backend/app/domain/services/tool_event_handler.py` (extend)

After tool execution completes, log to `tool_logs` collection:
```python
async def _log_tool_to_vectors(self, tool_name, input_summary, outcome, error_type, session_id, user_id):
    embedding = await embedding_client.embed(f"{tool_name}: {input_summary}")
    await qdrant.upsert("tool_logs", ...)
```

Wrap in try/except — tool logging must never block execution.

---

### Phase 3: Multi-Collection Setup (Priority: HIGH)
**Effort**: Medium — collection creation + repository methods
**Risk**: Low — additive, doesn't modify existing behavior

#### 3.1 Extend QdrantStorage for multi-collection
**File**: `backend/app/infrastructure/storage/qdrant.py`

```python
COLLECTIONS = {
    "user_knowledge": VectorParams(size=1536, distance=Distance.COSINE),
    "task_artifacts": VectorParams(size=1536, distance=Distance.COSINE),
    "tool_logs": VectorParams(size=1536, distance=Distance.COSINE),
    "reasoning_paths": VectorParams(size=1536, distance=Distance.COSINE),
    "semantic_cache": VectorParams(size=1536, distance=Distance.COSINE),
}

async def _ensure_collections(self) -> None:
    """Create all collections if they don't exist."""
    existing = await self._client.get_collections()
    existing_names = {c.name for c in existing.collections}
    for name, params in COLLECTIONS.items():
        if name not in existing_names:
            await self._client.create_collection(name, vectors_config=params)
```

Replace the single `_ensure_collection()` with `_ensure_collections()`.

#### 3.2 Collection-specific repository classes
Create thin repository wrappers for each collection:

**Files** (NEW):
- `infrastructure/repositories/qdrant_task_repository.py` — task artifacts CRUD + search
- `infrastructure/repositories/qdrant_tool_log_repository.py` — tool log CRUD + search
- `infrastructure/repositories/qdrant_reasoning_repository.py` — reasoning paths (Phase 2)

Each follows the same pattern as `QdrantMemoryRepository` but with collection-specific payloads and filters.

#### 3.3 Migrate `agent_memories` → `user_knowledge`
Use the existing `scripts/migrate_to_qdrant.py` as a template. Add a migration that:
1. Copies all points from `agent_memories` to `user_knowledge`
2. Adds alias so existing code works during transition
3. Eventually remove the old collection

---

### Phase 4: Role-Scoped Memory Access (Priority: MEDIUM)
**Effort**: Medium — filter logic + prompt injection
**Risk**: Low — additive enhancement to existing retrieval

#### 4.1 Role Context Wrappers
**File**: `backend/app/domain/services/memory_service.py` (extend)

Each agent role gets a scoped retrieval method:

```python
class RoleScopedMemory:
    """Provides role-specific memory access patterns."""

    def __init__(self, memory_service: MemoryService, role: str, user_id: str):
        self._service = memory_service
        self._role = role
        self._user_id = user_id

    async def get_context(self, task_description: str) -> str:
        """Get role-appropriate memories formatted for context injection."""
        # Role-specific type filters
        ROLE_MEMORY_TYPES = {
            "planner": [MemoryType.TASK_OUTCOME, MemoryType.ERROR_PATTERN, MemoryType.PROCEDURE],
            "executor": [MemoryType.PROCEDURE, MemoryType.FACT, MemoryType.PROJECT_CONTEXT],
            "researcher": [MemoryType.FACT, MemoryType.ENTITY, MemoryType.PROJECT_CONTEXT],
        }
        types = ROLE_MEMORY_TYPES.get(self._role, list(MemoryType))

        memories = await self._service.retrieve_relevant(
            user_id=self._user_id,
            context=task_description,
            memory_types=types,
            limit=10,
        )
        return await self._service.format_memories_for_context(memories)
```

#### 4.2 Inject into agent constructors
Pass `RoleScopedMemory` to PlannerAgent (role="planner"), ExecutionAgent (role="executor"), etc.

The existing `execution.py:197` and `planner.py:289` call sites become:
```python
# Before: raw memory_service.retrieve_for_task(...)
# After: self._scoped_memory.get_context(task_description)
```

---

### Phase 5: Cross-Session Intelligence (Priority: MEDIUM)
**Effort**: Large — new retrieval patterns, prompt engineering
**Risk**: Medium — impacts agent behavior, needs testing

#### 5.1 Similar task retrieval
When starting a new task, search `task_artifacts` for similar past tasks:

```python
async def find_similar_tasks(self, user_id: str, task_description: str, limit: int = 5):
    """Find past tasks similar to the current one."""
    embedding = await self._generate_embedding(task_description)
    results = await qdrant.search("task_artifacts", embedding, filter={"user_id": user_id}, limit=limit)
    return results
```

Inject findings into planner context: "You've done similar tasks before. Here's what worked/failed: ..."

#### 5.2 Error pattern recall
Before execution, retrieve relevant error patterns:

```python
# In execution agent, before running tools:
error_patterns = await memory_service.retrieve_relevant(
    user_id, context=f"Using {tool_name} for {task_description}",
    memory_types=[MemoryType.ERROR_PATTERN],
    limit=3,
)
if error_patterns:
    # Inject: "Watch out for these known issues: ..."
```

This connects to the existing `ErrorPatternAnalyzer.load_user_patterns()`.

#### 5.3 User preference application
Retrieve and apply user preferences at session start:

```python
async def get_user_preferences(self, user_id: str) -> str:
    """Get user preferences for context injection."""
    prefs = await memory_service.retrieve_relevant(
        user_id, context="user preferences and working style",
        memory_types=[MemoryType.PREFERENCE],
        limit=10,
    )
    return format_preferences_for_prompt(prefs)
```

#### 5.4 Stuck detection enhancement
Enhance the existing `stuck_detector.py` to compare current state against historical stuck states:

```python
# After detecting stuck locally, check if this pattern was seen before
similar_stucks = await qdrant.search("tool_logs",
    embedding=current_state_embedding,
    filter={"outcome": "failure", "user_id": user_id},
    limit=3,
)
if similar_stucks:
    # Inject recovery guidance from past successful recoveries
```

---

### Phase 6: Enable Semantic Cache (Priority: LOW)
**Effort**: Small — infrastructure exists, just enable
**Risk**: Low — behind feature flag

#### 6.1 Create embedding client
As noted in Phase 1.3, create the missing `get_embedding_client()`.

#### 6.2 Enable in config
```bash
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_THRESHOLD=0.92
SEMANTIC_CACHE_TTL_SECONDS=3600
```

#### 6.3 Integrate into LLM call path
In `anthropic_llm.py` and `openai_llm.py`, add cache check before API call:
```python
cache = await get_semantic_cache()
if cache:
    cached = await cache.get(prompt, context_hash)
    if cached:
        return cached
```

---

### Phase 7: Lifecycle Management (Priority: LOW)
**Effort**: Small — background tasks
**Risk**: Low — maintenance operations

#### 7.1 Background cleanup job
Add periodic cleanup (via FastAPI background task or startup scheduler):

```python
async def memory_cleanup_task():
    """Periodic memory maintenance."""
    while True:
        await asyncio.sleep(3600)  # Every hour
        try:
            # Remove expired memories
            await memory_service.cleanup(remove_expired=True, consolidate=False)

            # Consolidate similar memories (daily)
            if is_daily_window():
                for user_id in await get_active_users():
                    await memory_service.consolidate_memories(user_id)
        except Exception as e:
            logger.warning(f"Memory cleanup failed: {e}")
```

#### 7.2 Memory usage limits
Enforce `_max_memories_per_user = 10000` with LRU eviction:
- When at limit, remove lowest-importance, least-accessed memories
- Sync deletions to both MongoDB and Qdrant

#### 7.3 Qdrant collection maintenance
- Periodic payload index optimization
- Collection snapshot/backup (Qdrant API)
- Stale point cleanup (orphaned vectors)

---

## 5. File Change Summary

### New Files
| File | Purpose |
|------|---------|
| `infrastructure/external/embedding/client.py` | Shared embedding client |
| `infrastructure/external/embedding/__init__.py` | Package init |
| `infrastructure/repositories/qdrant_task_repository.py` | Task artifacts collection |
| `infrastructure/repositories/qdrant_tool_log_repository.py` | Tool logs collection |
| `infrastructure/repositories/qdrant_reasoning_repository.py` | Reasoning paths (Phase 5) |
| `domain/services/role_scoped_memory.py` | Role-based memory access |

### Modified Files
| File | Changes |
|------|---------|
| `infrastructure/storage/qdrant.py` | Multi-collection setup |
| `infrastructure/repositories/qdrant_memory_repository.py` | ABC inheritance |
| `main.py` | Wire vector repo + MemoryService at startup |
| `domain/services/agent_domain_service.py` | Post-session extraction hook |
| `domain/services/agent_task_runner.py` | Inject MemoryService |
| `domain/services/agents/execution.py` | Role-scoped memory |
| `domain/services/agents/planner.py` | Role-scoped memory |
| `domain/services/agents/reflection.py` | Historical context access |
| `domain/services/tool_event_handler.py` | Tool log vectorization |
| `domain/services/agents/stuck_detector.py` | Historical stuck patterns |
| `core/config.py` | New config fields for collections |
| `.env` | Enable feature flags |

### Tests Required
| Test File | Coverage |
|-----------|----------|
| `tests/test_qdrant_wiring.py` | Startup wiring, graceful degradation |
| `tests/test_memory_extraction.py` | Post-session extraction pipeline |
| `tests/test_role_scoped_memory.py` | Role-based retrieval filters |
| `tests/test_multi_collection.py` | Collection CRUD + search |
| `tests/test_embedding_client.py` | Embedding generation + caching |
| `tests/test_cross_session.py` | Similar task / error pattern recall |

---

## 6. Configuration Changes

### .env additions
```bash
# Phase 1: Enable existing features
FEATURE_PARALLEL_MEMORY=true

# Phase 3: Multi-collection names
QDRANT_USER_KNOWLEDGE_COLLECTION=user_knowledge
QDRANT_TASK_ARTIFACTS_COLLECTION=task_artifacts
QDRANT_TOOL_LOGS_COLLECTION=tool_logs
QDRANT_REASONING_PATHS_COLLECTION=reasoning_paths

# Phase 6: Semantic cache
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_THRESHOLD=0.92
SEMANTIC_CACHE_TTL_SECONDS=3600
```

### config.py additions
```python
# Multi-collection configuration
qdrant_user_knowledge_collection: str = "user_knowledge"
qdrant_task_artifacts_collection: str = "task_artifacts"
qdrant_tool_logs_collection: str = "tool_logs"
qdrant_reasoning_paths_collection: str = "reasoning_paths"
```

---

## 7. Risk Assessment & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| Qdrant unavailable | Memory falls back to MongoDB | Low | Graceful degradation already implemented |
| Embedding API failures | No vector indexing | Low | Fallback hash-based embeddings exist |
| Memory extraction noise | Low-quality memories stored | Medium | Confidence threshold (>0.7), dedup |
| Token overhead from context injection | Reduced context window | Medium | Budget cap (500 tokens for memories) |
| Migration data loss | Old memories lost | Low | Keep `agent_memories` alias during migration |
| Performance: embedding generation latency | Slower session completion | Low | Async post-session extraction, batch embeds |

---

## 8. Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Cross-session memory retrieval | 0 queries/session | 2-5 queries/session |
| Memory extraction rate | 0 memories/session | 3-10 memories/session |
| Similar task recall | None | Top-3 similar tasks for planning |
| Error pattern prevention | None | 50% reduction in repeated errors |
| Semantic cache hit rate | N/A (disabled) | 15-25% for similar queries |
| Qdrant uptime | Initialized but unused | Active reads/writes every session |

---

## 9. Implementation Order

```
Phase 1 (CRITICAL) ──→ Phase 2 (HIGH) ──→ Phase 3 (HIGH) ──→ Phase 4 (MEDIUM) ──→ Phase 5 (MEDIUM) ──→ Phase 6-7 (LOW)
     │                      │                    │                   │                    │
Wire existing          Memory extraction    Multi-collection    Role-scoped          Cross-session
infrastructure         pipeline             architecture        access               intelligence
     │                      │                    │                   │                    │
  ~2 hours              ~4 hours             ~4 hours            ~3 hours             ~6 hours
```

**Total estimated effort**: ~20 hours across all phases

Phase 1 unlocks Phases 2-3. Phase 4 depends on Phase 3. Phase 5 depends on Phases 2-4. Phases 6-7 are independent.
