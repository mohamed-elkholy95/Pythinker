# Roadmap Remaining Tasks - Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all remaining roadmap items across Phases 2-9 (35 actionable tasks after filtering already-complete items)

**Architecture:** Execute in priority order (P1 → P4), parallelizing independent tasks within each batch. Quick fixes first, then medium complexity, then large refactors.

**Tech Stack:** Python/FastAPI (backend), Vue 3/TypeScript (frontend), tenacity/retry (reliability), Pydantic v2 (models)

---

## Batch 1: Quick Wins (P1 — can execute in parallel)

### Task 1: DDD-012 — Fix CachedSessionRepository.update_by_id signature

**Files:**
- Modify: `backend/app/infrastructure/repositories/cached_session_repository.py:94`

- [ ] **Step 1: Fix signature to match Protocol**

Change `**updates: object` → `updates: dict[str, Any]` and forward correctly.

```python
async def update_by_id(self, session_id: str, updates: dict[str, Any]) -> None:
    await self._inner.update_by_id(session_id, updates)
    self._cache.pop(session_id, None)
```

- [ ] **Step 2: Verify type check passes**

Run: `cd backend && conda activate pythinker && python -m pyright app/infrastructure/repositories/cached_session_repository.py`

- [ ] **Step 3: Commit**

```bash
git add backend/app/infrastructure/repositories/cached_session_repository.py
git commit -m "fix(ddd): align CachedSessionRepository.update_by_id signature with Protocol"
```

---

### Task 2: REL-006 — Add retry to Qdrant operations

**Files:**
- Modify: `backend/app/infrastructure/repositories/qdrant_memory_repository.py`
- Modify: `backend/app/infrastructure/repositories/qdrant_task_repository.py`
- Modify: `backend/app/infrastructure/repositories/qdrant_tool_log_repository.py`

Uses existing `db_retry` decorator from `backend/app/core/retry.py`.

- [ ] **Step 1: Add db_retry to all Qdrant repository methods**

Import `from app.core.retry import db_retry` and apply `@db_retry` to all async methods that interact with Qdrant.

- [ ] **Step 2: Verify lint passes**

Run: `cd backend && ruff check app/infrastructure/repositories/qdrant_*.py`

- [ ] **Step 3: Commit**

```bash
git add backend/app/infrastructure/repositories/qdrant_*.py
git commit -m "feat(reliability): add db_retry to all Qdrant repository operations"
```

---

### Task 3: REL-008 — Add retry to MongoDB memory create

**Files:**
- Modify: `backend/app/infrastructure/repositories/mongo_memory_repository.py`

- [ ] **Step 1: Add db_retry to create/create_many**

Import `from app.core.retry import db_retry` and apply to `create()` and `create_many()`.

- [ ] **Step 2: Commit**

```bash
git add backend/app/infrastructure/repositories/mongo_memory_repository.py
git commit -m "feat(reliability): add db_retry to MongoDB memory create operations"
```

---

### Task 4: HTTP-003 — Remove deprecated httpx from DockerSandbox

**Files:**
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py`

- [ ] **Step 1: Remove deprecated .client property and _client field**
- [ ] **Step 2: Replace SSE httpx.AsyncClient with HTTPClientPool**
- [ ] **Step 3: Remove manual client cleanup code**
- [ ] **Step 4: Commit**

---

### Task 5: FE-012 — Type the mitt event bus

**Files:**
- Modify: `frontend/src/utils/eventBus.ts`

- [ ] **Step 1: Define typed events interface**
- [ ] **Step 2: Create typed mitt instance**
- [ ] **Step 3: Fix all consumers**
- [ ] **Step 4: Commit**

---

### Task 6: FE-015 + FE-016 + FE-018 — Accessibility fixes for SkillCreatorDialog

**Files:**
- Modify: `frontend/src/components/settings/SkillCreatorDialog.vue`

- [ ] **Step 1: Add aria-labels to icon-only buttons**
- [ ] **Step 2: Add role="dialog", aria-modal, aria-labelledby**
- [ ] **Step 3: Add focus trap (manual or via focus-trap library)**
- [ ] **Step 4: Add aria-describedby to all form fields**
- [ ] **Step 5: Add Escape key handler**
- [ ] **Step 6: Commit**

---

### Task 7: CFG-004 — Externalize SSE operational parameters

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/interfaces/api/session_routes.py`

- [ ] **Step 1: Add settings fields**
- [ ] **Step 2: Replace hardcoded values**
- [ ] **Step 3: Commit**

---

### Task 8: CLEAN-009 — Align timestamp types

**Files:**
- Modify: `backend/app/domain/models/research_trace.py`

- [ ] **Step 1: Change float timestamp to datetime**
- [ ] **Step 2: Update consumers**
- [ ] **Step 3: Commit**

---

### Task 9: PERF-006 — Cursor-based pagination for list_users

**Files:**
- Modify: `backend/app/infrastructure/repositories/user_repository.py`
- Modify: `backend/app/domain/repositories/user_repository.py` (Protocol)

- [ ] **Step 1: Add cursor parameter to Protocol and implementation**
- [ ] **Step 2: Implement cursor-based query using _id**
- [ ] **Step 3: Commit**

---

### Task 10: API-011 — Fix channel_link_routes DI

**Files:**
- Modify: `backend/app/interfaces/api/channel_link_routes.py`

- [ ] **Step 1: Replace direct HTTPClientPool call with Depends()**
- [ ] **Step 2: Commit**

---

### Task 11: FE-009 — Add visibility check to ShellToolView polling

**Files:**
- Modify: `frontend/src/components/toolViews/ShellToolView.vue`

- [ ] **Step 1: Add document visibility detection**
- [ ] **Step 2: Pause polling when tab is inactive**
- [ ] **Step 3: Commit**

---

### Task 12: FE-014 — Type result and content props

**Files:**
- Modify: `frontend/src/components/toolViews/GenericContentView.vue`

- [ ] **Step 1: Define ToolResult type**
- [ ] **Step 2: Update props**
- [ ] **Step 3: Commit**

---

## Batch 2: Medium Complexity (P1-P2)

### Task 13: DDD-011 — CachedSessionRepository missing Protocol methods

**Files:**
- Modify: `backend/app/infrastructure/repositories/cached_session_repository.py`

- [ ] **Step 1: Implement all 19 missing methods with cache-aside pattern**
- [ ] **Step 2: Commit**

---

### Task 14: DDD-014 — Unify memory repository contracts

**Files:**
- Modify: `backend/app/domain/repositories/memory_repository.py`
- Modify: `backend/app/domain/repositories/vector_memory_repository.py`

- [ ] **Step 1: Design unified contract**
- [ ] **Step 2: Update implementations**
- [ ] **Step 3: Commit**

---

### Task 15: CFG-005 — Refresh token rotation

**Files:**
- Modify: `backend/app/interfaces/api/auth_routes.py`
- Modify: `backend/app/application/services/auth_service.py`

- [ ] **Step 1: Issue new refresh token on refresh**
- [ ] **Step 2: Invalidate old refresh token**
- [ ] **Step 3: Commit**

---

### Task 16: PERF-001 — Eliminate Python cosine similarity

**Files:**
- Modify: `backend/app/domain/services/retrieval/mmr.py`

- [ ] **Step 1: Use numpy vectorized operations**
- [ ] **Step 2: Commit**

---

### Task 17: PERF-007 — shallowRef for messages array

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`

- [ ] **Step 1: Replace reactive messages with shallowRef**
- [ ] **Step 2: Update mutation patterns**
- [ ] **Step 3: Commit**

---

### Task 18: API-003 — Implement sandbox callback routes

**Files:**
- Modify: `backend/app/interfaces/api/sandbox_callback_routes.py`

- [ ] **Step 1: Implement event callback logic**
- [ ] **Step 2: Implement progress callback logic**
- [ ] **Step 3: Commit**

---

## Batch 3: ChatPage Decomposition (P2)

### Task 19-23: FE-001 to FE-005

These are interdependent ChatPage refactors — execute sequentially.

---

## Batch 4: Large Refactors (P1 — needs dedicated plans)

### Task 24: DDD-004 — agent_task_runner.py infrastructure imports
### Task 25: DDD-006 — get_settings across 55 domain files (incremental)
### Task 26: REL-009 — Propagate sandbox crash to agent orchestrator

---

## Batch 5: Phase 6 — Test Coverage & CI/CD (P2)

### Tasks 27-47: CI-001 through DOCKER-004

These are CI/CD pipeline and test infrastructure tasks — separate execution plan needed.

---

## Updated Roadmap Marks (Already Complete)

- [x] **API-004** — OpenAPI annotations already present
- [x] **API-006** — canvas_routes already uses Depends()
- [x] **API-007** — connector_routes already uses Depends()
- [x] **API-008** — usage_routes already uses Depends()
- [x] **API-009** — metrics_routes already uses Depends()
- [x] **API-010** — auth_routes already uses Depends()
- [x] **FE-008** — useTaskTimer reference counting already solid
- [x] **FE-017** — Session cards already keyboard accessible
- [x] **REL-007** — MinIO already has custom retry with backoff+metrics
