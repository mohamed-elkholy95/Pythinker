# Code Quality Report Fixes - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all verified issues from CODE_QUALITY_REPORT.md across security, dead code, architecture, and code smells.

**Architecture:** Systematic cleanup working outward from security fixes, through dead code removal, architecture corrections, and code smell fixes. Each task is independent and safe to commit atomically.

**Tech Stack:** Python/FastAPI (backend), Vue 3/TypeScript (frontend), Ruff (linting), pytest (testing)

**Pre-requisites:** Priority 1 runtime bugs already fixed in prior session (7/7 complete).

---

## Phase 1: Security Fixes (Priority 2)

### Task 1: Add auth to maintenance endpoints

**Files:**
- Modify: `backend/app/interfaces/api/maintenance_routes.py`

**Step 1: Add auth import and dependency to all endpoints**

Add `get_current_user` dependency to every endpoint in this file. The standard pattern used in `session_routes.py`:

```python
from app.interfaces.api.dependencies import get_current_user
from app.domain.models.user import User
from fastapi import Depends
```

Every endpoint gets:
```python
current_user: User = Depends(get_current_user),
```

Apply to all 5 endpoints:
- `GET /maintenance/health/session/{session_id}`
- `POST /maintenance/cleanup/attachments`
- `GET /maintenance/cleanup/attachments/preview`
- `POST /maintenance/cleanup/stale-sessions`
- `GET /maintenance/cleanup/stale-sessions/preview`

**Step 2: Run linter**

Run: `source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && cd /Users/panda/Desktop/Projects/pyth-main/backend && ruff check app/interfaces/api/maintenance_routes.py`
Expected: All checks passed

**Step 3: Commit**

```bash
git add backend/app/interfaces/api/maintenance_routes.py
git commit -m "security: add authentication to maintenance endpoints"
```

---

### Task 2: Add auth to monitoring endpoints

**Files:**
- Modify: `backend/app/interfaces/api/monitoring_routes.py`

**Step 1: Add auth dependency to all 7 endpoints**

Same pattern as Task 1. Add `get_current_user` import and `current_user: User = Depends(get_current_user)` to all endpoints:
- `GET /monitoring/health`
- `GET /monitoring/health/{component}`
- `GET /monitoring/errors`
- `GET /monitoring/sandboxes`
- `GET /monitoring/status`
- `POST /monitoring/health/start`
- `POST /monitoring/health/stop`

**Step 2: Run linter**

Run: `ruff check app/interfaces/api/monitoring_routes.py`
Expected: All checks passed

**Step 3: Commit**

```bash
git add backend/app/interfaces/api/monitoring_routes.py
git commit -m "security: add authentication to monitoring endpoints"
```

---

### Task 3: Add auth to metrics endpoints

**Files:**
- Modify: `backend/app/interfaces/api/metrics_routes.py`

**Step 1: Add auth dependency to all endpoints**

Same pattern. Add `get_current_user` to all 15+ endpoints. The `GET /metrics` prometheus scrape endpoint can keep optional auth or stay public if needed for automated scraping, but all others (especially `POST /metrics/agent/reset`) must require auth.

For the prometheus endpoint specifically, use optional auth:
```python
from app.interfaces.api.dependencies import get_optional_current_user
```

For all other endpoints, use required auth with `get_current_user`.

**Step 2: Run linter**

Run: `ruff check app/interfaces/api/metrics_routes.py`
Expected: All checks passed

**Step 3: Commit**

```bash
git add backend/app/interfaces/api/metrics_routes.py
git commit -m "security: add authentication to metrics endpoints"
```

---

### Task 4: Add auth to rating endpoint

**Files:**
- Modify: `backend/app/interfaces/api/rating_routes.py`

**Step 1: Add auth dependency**

Add `get_current_user` to the single `POST /ratings` endpoint.

**Step 2: Run linter**

Run: `ruff check app/interfaces/api/rating_routes.py`
Expected: All checks passed

**Step 3: Commit**

```bash
git add backend/app/interfaces/api/rating_routes.py
git commit -m "security: add authentication to rating endpoint"
```

---

### Task 5: Add ownership verification to clear_unread_message_count

**Files:**
- Modify: `backend/app/application/services/agent_service.py:369-373`

**Step 1: Add ownership check**

Replace current method:
```python
async def clear_unread_message_count(self, session_id: str, user_id: str) -> None:
    """Clear the unread message count for a session, ensuring it belongs to the user"""
    logger.info(f"Clearing unread message count for session {session_id} for user {user_id}")
    await self._session_repository.update_unread_message_count(session_id, 0)
    logger.info(f"Unread message count cleared for session {session_id}")
```

With (matching pattern from delete_session, stop_session, rename_session, etc.):
```python
async def clear_unread_message_count(self, session_id: str, user_id: str) -> None:
    """Clear the unread message count for a session, ensuring it belongs to the user"""
    logger.info(f"Clearing unread message count for session {session_id} for user {user_id}")
    session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
    if not session:
        logger.error(f"Session {session_id} not found for user {user_id}")
        raise RuntimeError("Session not found")
    await self._session_repository.update_unread_message_count(session_id, 0)
    logger.info(f"Unread message count cleared for session {session_id}")
```

**Step 2: Run linter**

Run: `ruff check app/application/services/agent_service.py`
Expected: All checks passed

**Step 3: Commit**

```bash
git add backend/app/application/services/agent_service.py
git commit -m "security: add ownership verification to clear_unread_message_count"
```

---

### Task 6: Remove CORS override on VNC screenshot endpoint

**Files:**
- Modify: `backend/app/interfaces/api/session_routes.py`

**Step 1: Remove manual CORS headers**

Find the `get_vnc_screenshot` endpoint (around line 547-604). In the Response headers, remove these manual CORS overrides:
```python
"Access-Control-Allow-Origin": "*",
"Access-Control-Allow-Methods": "GET, OPTIONS",
"Access-Control-Allow-Headers": "*",
```

Keep other headers like `Cache-Control`. The app-level CORS middleware handles CORS properly.

**Step 2: Run linter**

Run: `ruff check app/interfaces/api/session_routes.py`
Expected: All checks passed

**Step 3: Commit**

```bash
git add backend/app/interfaces/api/session_routes.py
git commit -m "security: remove manual CORS override on VNC screenshot endpoint"
```

---

## Phase 2: Dead Code Removal (Priority 3)

### Task 7: Delete confirmed dead backend files

**Files:**
- Delete: `backend/app/application/services/scheduler_service.py` (265 lines)
- Delete: `backend/app/infrastructure/repositories/mongo_provenance_repository.py` (507 lines)

**Step 1: Verify no imports exist**

Run: `grep -r "scheduler_service\|SchedulerService" backend/app/ --include="*.py" -l`
Run: `grep -r "mongo_provenance_repository\|MongoProvenanceRepository" backend/app/ --include="*.py" -l`

Expected: No results (or only the files themselves)

**Step 2: Delete the files**

```bash
rm backend/app/application/services/scheduler_service.py
rm backend/app/infrastructure/repositories/mongo_provenance_repository.py
```

**Step 3: Run tests**

Run: `pytest tests/ -x -q --timeout=30`
Expected: All tests pass (same as baseline)

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove dead SchedulerService and MongoProvenanceRepository (772 lines)"
```

---

### Task 8: Delete confirmed dead frontend files

**Files:**
- Delete: `frontend/src/types/select.ts` (25 lines)
- Delete: `frontend/src/utils/debounce.ts` (56 lines)

**Step 1: Verify no imports exist**

Run: `grep -r "select" frontend/src/ --include="*.ts" --include="*.vue" -l | grep -v node_modules` (check for `types/select` specifically)
Run: `grep -r "debounce" frontend/src/ --include="*.ts" --include="*.vue" -l`

Expected: No imports of these specific files

**Step 2: Delete the files**

```bash
rm frontend/src/types/select.ts
rm frontend/src/utils/debounce.ts
```

**Step 3: Run type check**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run type-check`
Expected: No errors

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove dead select types and debounce utility (81 lines)"
```

---

### Task 9: Delete orphaned frontend icon components

**Files:**
- Delete: `frontend/src/components/icons/ManusIcon.vue`
- Delete: `frontend/src/components/icons/ManusLogoTextIcon.vue`
- Delete: `frontend/src/components/icons/ManusTextIcon.vue`
- Delete: `frontend/src/components/icons/SpinnigIcon.vue`
- Delete: `frontend/src/components/icons/ClearIcon.vue`
- Delete: `frontend/src/components/icons/AttachmentIcon.vue`

**Step 1: Verify no imports**

Run: `grep -r "ManusIcon\|ManusLogoTextIcon\|ManusTextIcon\|SpinnigIcon\|ClearIcon\|AttachmentIcon" frontend/src/ --include="*.vue" --include="*.ts" -l`

Expected: Only the files themselves

**Step 2: Delete all 6 files**

```bash
rm frontend/src/components/icons/ManusIcon.vue
rm frontend/src/components/icons/ManusLogoTextIcon.vue
rm frontend/src/components/icons/ManusTextIcon.vue
rm frontend/src/components/icons/SpinnigIcon.vue
rm frontend/src/components/icons/ClearIcon.vue
rm frontend/src/components/icons/AttachmentIcon.vue
```

**Step 3: Run type check and lint**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run type-check && bun run lint`
Expected: No errors

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove 6 orphaned icon components (Manus legacy, unused)"
```

---

### Task 10: Delete orphaned feature components

**Files:**
- Delete: `frontend/src/components/CDPScreencastViewer.vue`
- Delete: `frontend/src/components/WorkspacePanel.vue`
- Delete: `frontend/src/components/WorkspaceTemplateDialog.vue`
- Delete: `frontend/src/components/SkillDeliveryCard.vue`
- Delete: `frontend/src/components/SkillPill.vue`
- Delete: `frontend/src/components/SkillViewerModal.vue`
- Delete: `frontend/src/components/SkillsPopover.vue`
- Delete: `frontend/src/components/StepThought.vue`
- Delete: `frontend/src/components/AutocompleteDropdown.vue`
- Delete: `frontend/src/components/shared/LottieAnimation.vue`
- Delete: `frontend/src/components/AgentComputerModal.vue`
- Delete: `frontend/src/components/AgentComputerView.vue` (only used by AgentComputerModal)

**Step 1: Verify no imports for each**

Run: `grep -r "CDPScreencastViewer\|WorkspacePanel\|WorkspaceTemplateDialog\|SkillDeliveryCard\|SkillPill\|SkillViewerModal\|SkillsPopover\|StepThought\|AutocompleteDropdown\|LottieAnimation\|AgentComputerModal\|AgentComputerView" frontend/src/ --include="*.vue" --include="*.ts" -l`

Expected: Only the files themselves and AgentComputerView referenced by AgentComputerModal (both being deleted)

**Step 2: Delete all 12 files**

```bash
rm frontend/src/components/CDPScreencastViewer.vue
rm frontend/src/components/WorkspacePanel.vue
rm frontend/src/components/WorkspaceTemplateDialog.vue
rm frontend/src/components/SkillDeliveryCard.vue
rm frontend/src/components/SkillPill.vue
rm frontend/src/components/SkillViewerModal.vue
rm frontend/src/components/SkillsPopover.vue
rm frontend/src/components/StepThought.vue
rm frontend/src/components/AutocompleteDropdown.vue
rm frontend/src/components/shared/LottieAnimation.vue
rm frontend/src/components/AgentComputerModal.vue
rm frontend/src/components/AgentComputerView.vue
```

**Step 3: Run type check and lint**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run type-check && bun run lint`
Expected: No errors

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove 12 orphaned feature components (CDP, Workspace, Skills, etc.)"
```

---

## Phase 3: Architecture Fixes (Priority 4)

### Task 11: Fix TokenLimitExceededError duplication across LLM adapters

**Files:**
- Modify: `backend/app/infrastructure/external/llm/anthropic_llm.py`
- Modify: `backend/app/infrastructure/external/llm/ollama_llm.py`

**Step 1: Fix anthropic_llm.py**

Remove the local `TokenLimitExceededError` class definition (lines 35-38):
```python
class TokenLimitExceededError(Exception):
    """Raised when the token limit is exceeded."""
    pass
```

Replace with import from domain:
```python
from app.domain.services.agents.error_handler import TokenLimitExceededError
```

**Step 2: Fix ollama_llm.py**

Remove the local `TokenLimitExceededError` class definition (lines 27-30):
```python
class TokenLimitExceededError(Exception):
    """Raised when the token limit is exceeded."""
    pass
```

Replace with import from domain:
```python
from app.domain.services.agents.error_handler import TokenLimitExceededError
```

**Step 3: Run linter**

Run: `ruff check app/infrastructure/external/llm/anthropic_llm.py app/infrastructure/external/llm/ollama_llm.py`
Expected: All checks passed

**Step 4: Run tests**

Run: `pytest tests/ -x -q --timeout=30 -k "llm or anthropic or ollama"`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/llm/anthropic_llm.py backend/app/infrastructure/external/llm/ollama_llm.py
git commit -m "refactor: use domain TokenLimitExceededError in all LLM adapters"
```

---

### Task 12: Fix LLM Protocol missing enable_caching param

**Files:**
- Modify: `backend/app/domain/external/llm.py`

**Step 1: Read the current Protocol definition**

Read `backend/app/domain/external/llm.py` and find the `ask()` and `ask_stream()` method signatures.

**Step 2: Add `enable_caching` parameter**

Add `enable_caching: bool = True` to the `ask()` and `ask_stream()` method signatures in the Protocol class, matching the implementations in all 3 adapters.

**Step 3: Run linter**

Run: `ruff check app/domain/external/llm.py`
Expected: All checks passed

**Step 4: Commit**

```bash
git add backend/app/domain/external/llm.py
git commit -m "fix: add enable_caching param to LLM Protocol to match implementations"
```

---

### Task 13: Fix concrete OpenAILLM imports violating DDD

**Files:**
- Modify: `backend/app/infrastructure/external/browser/playwright_browser.py:15`
- Modify: `backend/app/interfaces/dependencies.py:24`
- Modify: `backend/app/infrastructure/utils/llm_json_parser.py:8`

**Step 1: Read each file to understand how OpenAILLM is used**

Read each file to understand the actual usage. If OpenAILLM is used only for its type or for `ask()`/`ask_stream()` methods, replace with the `LLM` Protocol import.

For each file, replace:
```python
from app.infrastructure.external.llm.openai_llm import OpenAILLM
```
With:
```python
from app.domain.external.llm import LLM
```

And update type annotations from `OpenAILLM` to `LLM`.

If a concrete feature of OpenAILLM is needed (like specific constructor), use the factory:
```python
from app.infrastructure.external.llm import get_llm
```

**Step 2: Run linter**

Run: `ruff check app/infrastructure/external/browser/playwright_browser.py app/interfaces/dependencies.py app/infrastructure/utils/llm_json_parser.py`
Expected: All checks passed

**Step 3: Run tests**

Run: `pytest tests/ -x -q --timeout=30`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/infrastructure/external/browser/playwright_browser.py backend/app/interfaces/dependencies.py backend/app/infrastructure/utils/llm_json_parser.py
git commit -m "refactor: replace concrete OpenAILLM imports with LLM Protocol"
```

---

### Task 14: Remove duplicate get_llm() in factory.py

**Files:**
- Modify: `backend/app/infrastructure/external/llm/factory.py`

**Step 1: Remove the duplicate alias**

Remove the `get_llm()` function at lines 118-120 in factory.py. The canonical version is in `__init__.py` with `@lru_cache`.

**Step 2: Verify no direct imports of factory.get_llm**

Run: `grep -r "from.*factory import.*get_llm" backend/ --include="*.py"`

If any imports exist, update them to import from `app.infrastructure.external.llm` instead.

**Step 3: Run linter and tests**

Run: `ruff check app/infrastructure/external/llm/factory.py && pytest tests/ -x -q --timeout=30`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/infrastructure/external/llm/factory.py
git commit -m "refactor: remove duplicate get_llm alias from factory module"
```

---

## Phase 4: Code Smell Fixes (Priority 5)

### Task 15: Fix broken reactivity in ToolUse.vue

**Files:**
- Modify: `frontend/src/components/ToolUse.vue:59`

**Step 1: Fix ref to toRef**

Read the file. Find line 59 where `ref(props.tool)` is used. Replace with:
```typescript
import { toRef } from 'vue'
// ...
const tool = toRef(props, 'tool')
```

Or if using Vue 3.3+ syntax:
```typescript
const tool = toRef(() => props.tool)
```

**Step 2: Run type check and lint**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run type-check && bun run lint`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/ToolUse.vue
git commit -m "fix: use toRef for reactive prop access in ToolUse"
```

---

### Task 16: Fix hardcoded "Manus" brand name

**Files:**
- Modify: `frontend/src/components/login/RegisterForm.vue:264`

**Step 1: Replace brand reference**

Find "Manus" on line 264 and replace with "Pythinker".

**Step 2: Run lint**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run lint`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/login/RegisterForm.vue
git commit -m "fix: replace legacy Manus branding with Pythinker"
```

---

### Task 17: Fix memory leak - keydown listener in AgentComputerModal

**Note:** If Task 10 deletes AgentComputerModal.vue, skip this task.

**Files:**
- Modify: `frontend/src/components/AgentComputerModal.vue:79-81`

**Step 1: Add cleanup for keydown listener**

Find the `onMounted` hook that adds a `keydown` listener. Add a corresponding `onUnmounted` to remove it:

```typescript
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})
```

**Step 2: Commit**

```bash
git add frontend/src/components/AgentComputerModal.vue
git commit -m "fix: clean up keydown listener on unmount in AgentComputerModal"
```

---

### Task 18: Fix memory leak - auth:logout listener never removed

**Files:**
- Modify: `frontend/src/composables/useAuth.ts:219-223`

**Step 1: Read the file and find the auth:logout listener**

Find where `auth:logout` event listener is added. Add cleanup in `onUnmounted` or return a cleanup function.

**Step 2: Run type check**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/composables/useAuth.ts
git commit -m "fix: clean up auth:logout event listener to prevent memory leak"
```

---

### Task 19: Remove console.log statements from production code

**Files:**
- Modify: `frontend/src/components/toolViews/FileToolView.vue:157`
- Modify: `frontend/src/components/VNCViewer.vue` (7 occurrences)
- Modify: `frontend/src/components/AgentComputerView.vue` (2 occurrences - skip if deleted in Task 10)
- Modify: `frontend/src/components/login/ResetPasswordForm.vue:160`

**Step 1: Remove console.log statements**

For each file, remove or convert `console.log` to proper logging. If the log is truly for debugging, remove it. If it provides operational value, keep it.

**Step 2: Run lint**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run lint`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/toolViews/FileToolView.vue frontend/src/components/VNCViewer.vue frontend/src/components/login/ResetPasswordForm.vue
git commit -m "chore: remove console.log statements from production code"
```

---

### Task 20: Run full test suite and verify everything passes

**Step 1: Backend tests**

Run: `source /Users/panda/anaconda3/etc/profile.d/conda.sh && conda activate pythinker && cd /Users/panda/Desktop/Projects/pyth-main/backend && pytest tests/ -x -q --timeout=30`
Expected: All pass (except the pre-existing structlog recursion issue)

**Step 2: Frontend checks**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/frontend && bun run type-check && bun run lint`
Expected: No errors

**Step 3: Backend lint**

Run: `cd /Users/panda/Desktop/Projects/pyth-main/backend && ruff check . && ruff format --check .`
Expected: All pass

---

## Summary

| Phase | Tasks | Focus | Lines Removed |
|-------|-------|-------|---------------|
| 1: Security | Tasks 1-6 | Auth on 28+ endpoints, ownership check, CORS | ~0 (additions) |
| 2: Dead Code | Tasks 7-10 | Delete 20 files | ~1,700+ lines |
| 3: Architecture | Tasks 11-14 | Fix DDD violations, dedup errors | ~30 lines |
| 4: Code Smells | Tasks 15-19 | Reactivity, branding, leaks, logs | ~20 lines |
| 5: Verify | Task 20 | Full test suite | 0 |

**Total: 20 tasks across 4 phases + final verification**

**Items explicitly NOT in this plan (require separate design work):**
- God class refactoring (plan_act.py, ChatPage.vue, etc.) - needs architectural design
- Duplicate system consolidation (CriticAgent, checkpoint managers) - needs analysis of which to keep
- Frontend test creation - needs test strategy document
- Coverage threshold increase - depends on test creation
- Form validation composable extraction - needs design
- Shared LLM adapter base class extraction - needs design
