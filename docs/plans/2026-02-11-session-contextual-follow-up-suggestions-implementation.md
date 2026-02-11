# Session-Contextual Follow-Up Suggestions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure the "Suggested follow-ups" section appears after task completion with suggestions grounded in the same session, and preserve context when users click a suggestion.

**Architecture:** Keep the existing suggestion UI, but make suggestion generation and selection context-aware end-to-end. Add lightweight follow-up metadata in API contracts, skip context-free fast paths for suggestion clicks, and enrich backend suggestion generation with session anchor context.

**Tech Stack:** Vue 3 + TypeScript (frontend), FastAPI + Pydantic v2 + Python (backend), SSE events, pytest, vitest.

---

### Task 1: Add Suggestion Follow-Up Context Contract (Frontend + Backend)

**Files:**
- Modify: `frontend/src/api/agent.ts`
- Modify: `frontend/src/types/event.ts`
- Modify: `backend/app/interfaces/schemas/session.py`
- Modify: `backend/app/domain/models/message.py`
- Modify: `backend/app/domain/models/event.py`
- Modify: `backend/app/interfaces/schemas/event.py`
- Test: `frontend/tests/api/agent.suggestion-followup.spec.ts` (new)
- Test: `backend/tests/interfaces/schemas/test_session_chat_request_follow_up.py` (new)

**Step 1: Write the failing tests**

```ts
// frontend/tests/api/agent.suggestion-followup.spec.ts
it('includes follow_up payload in chat request when provided', async () => {
  // expect request body.follow_up.selected_suggestion to exist
});
```

```python
# backend/tests/interfaces/schemas/test_session_chat_request_follow_up.py

def test_chat_request_accepts_follow_up_payload() -> None:
    payload = {
        "message": "Can you expand on the migration risk?",
        "follow_up": {
            "selected_suggestion": "Can you expand on the migration risk?",
            "anchor_event_id": "evt_123",
            "source": "suggestion_click",
        },
    }
    req = ChatRequest.model_validate(payload)
    assert req.follow_up is not None
```

**Step 2: Run tests to verify they fail**

Run:
```bash
cd frontend && bun run vitest frontend/tests/api/agent.suggestion-followup.spec.ts
```
Expected: FAIL because `follow_up` is not in request contract.

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/interfaces/schemas/test_session_chat_request_follow_up.py
```
Expected: FAIL because `ChatRequest` has no `follow_up` field.

**Step 3: Write minimal implementation**

- Add `follow_up` optional object to frontend chat request payload.
- Add `follow_up` typed schema in backend `ChatRequest`.
- Add optional follow-up fields to domain `Message` so the flow layer can consume context.
- Add optional suggestion metadata fields to `SuggestionEvent`/SSE schema for anchor provenance.

**Step 4: Run tests to verify they pass**

Run:
```bash
cd frontend && bun run vitest frontend/tests/api/agent.suggestion-followup.spec.ts
```
Expected: PASS.

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/interfaces/schemas/test_session_chat_request_follow_up.py
```
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/api/agent.ts frontend/src/types/event.ts backend/app/interfaces/schemas/session.py backend/app/domain/models/message.py backend/app/domain/models/event.py backend/app/interfaces/schemas/event.py frontend/tests/api/agent.suggestion-followup.spec.ts backend/tests/interfaces/schemas/test_session_chat_request_follow_up.py
git commit -m "feat: add follow-up context contract for suggestion clicks"
```

---

### Task 2: Send Suggestion Selection Context from Chat UI

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue`
- Test: `frontend/tests/pages/ChatPage.suggestion-context.spec.ts` (new)

**Step 1: Write the failing test**

```ts
it('sends follow_up metadata when user clicks suggestion', async () => {
  // click suggestion
  // assert chatWithSession called with follow_up.source === 'suggestion_click'
  // assert anchor_event_id is from latest assistant/report event in this session
});
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd frontend && bun run vitest frontend/tests/pages/ChatPage.suggestion-context.spec.ts
```
Expected: FAIL because `handleSuggestionSelect` currently submits plain text only.

**Step 3: Write minimal implementation**

- Track current suggestion metadata in `ChatPage.vue` (anchor event id, source, optional excerpt).
- Update `handleSuggestionEvent` to store metadata from SSE suggestion events.
- Update `ensureCompletionSuggestions` fallback to create local metadata anchored to latest assistant/report event.
- Update `handleSuggestionSelect` and `chat()` to pass `follow_up` payload into `chatWithSession`.
- Clear follow-up metadata after submit to avoid leaking stale anchors.

**Step 4: Run test to verify it passes**

Run:
```bash
cd frontend && bun run vitest frontend/tests/pages/ChatPage.suggestion-context.spec.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.vue frontend/tests/pages/ChatPage.suggestion-context.spec.ts
git commit -m "feat: include session anchor metadata when suggestion is clicked"
```

---

### Task 3: Propagate Follow-Up Context Through Chat Pipeline

**Files:**
- Modify: `backend/app/interfaces/api/session_routes.py`
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/domain/services/agent_domain_service.py`
- Test: `backend/tests/application/services/test_agent_service_follow_up_context.py` (new)

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_chat_passes_follow_up_context_to_domain_service() -> None:
    # arrange AgentService with mocked domain service
    # call chat(..., follow_up={...})
    # assert _agent_domain_service.chat called with follow_up payload
```

**Step 2: Run test to verify it fails**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/application/services/test_agent_service_follow_up_context.py
```
Expected: FAIL because signatures do not include `follow_up`.

**Step 3: Write minimal implementation**

- Add `follow_up` parameter threading from route -> application service -> domain service.
- Include `follow_up` when creating user `MessageEvent` and task input `Message`.
- Preserve backwards compatibility by defaulting to `None`.

**Step 4: Run test to verify it passes**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/application/services/test_agent_service_follow_up_context.py
```
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/interfaces/api/session_routes.py backend/app/application/services/agent_service.py backend/app/domain/services/agent_domain_service.py backend/tests/application/services/test_agent_service_follow_up_context.py
git commit -m "feat: propagate follow-up context through chat service pipeline"
```

---

### Task 4: Force Contextual Routing for Suggestion-Clicked Follow-Ups

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/domain/services/flows/fast_path.py`
- Modify: `backend/tests/test_fast_path.py`
- Test: `backend/tests/domain/services/flows/test_plan_act_follow_up_context.py` (new)

**Step 1: Write the failing tests**

```python
# backend/tests/test_fast_path.py

def test_suggestion_click_follow_up_skips_fast_path() -> None:
    # with follow_up metadata present, routing should avoid context-free fast path
```

```python
# backend/tests/domain/services/flows/test_plan_act_follow_up_context.py
@pytest.mark.asyncio
async def test_plan_act_skips_fast_path_when_message_is_suggestion_click() -> None:
    # assert skip reason is contextual follow-up and full flow is used
```

**Step 2: Run tests to verify they fail**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/test_fast_path.py backend/tests/domain/services/flows/test_plan_act_follow_up_context.py
```
Expected: FAIL because current logic only matches static phrase patterns.

**Step 3: Write minimal implementation**

- Add explicit fast-path bypass when `message.follow_up.source == "suggestion_click"`.
- Keep legacy regex fallback in `is_suggestion_follow_up_message()` for old clients.
- Add clear skip reason logs for observability.

**Step 4: Run tests to verify they pass**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/test_fast_path.py backend/tests/domain/services/flows/test_plan_act_follow_up_context.py
```
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py backend/app/domain/services/flows/fast_path.py backend/tests/test_fast_path.py backend/tests/domain/services/flows/test_plan_act_follow_up_context.py
git commit -m "fix: bypass fast path for suggestion-click follow-up messages"
```

---

### Task 5: Generate Session-Anchored Suggestions at Task Completion

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py`
- Modify: `backend/app/domain/services/flows/discuss.py`
- Modify: `backend/tests/domain/services/flows/test_discuss.py`
- Test: `backend/tests/unit/agents/test_execution_suggestions.py` (new)

**Step 1: Write the failing tests**

```python
# backend/tests/unit/agents/test_execution_suggestions.py
@pytest.mark.asyncio
async def test_execution_suggestions_prompt_includes_user_request_and_summary_context() -> None:
    # assert llm.ask prompt includes both _user_request and completion summary excerpt

@pytest.mark.asyncio
async def test_execution_suggestion_event_includes_anchor_metadata() -> None:
    # assert SuggestionEvent contains anchor_event_id/source when report/message exists
```

```python
# backend/tests/domain/services/flows/test_discuss.py (extend existing)
@pytest.mark.asyncio
async def test_generated_discuss_suggestions_include_exchange_context_in_prompt() -> None:
    # verify user + assistant exchange are included in generation prompt
```

**Step 2: Run tests to verify they fail**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/unit/agents/test_execution_suggestions.py backend/tests/domain/services/flows/test_discuss.py
```
Expected: FAIL because execution suggestion prompt currently uses only title and has no anchor metadata.

**Step 3: Write minimal implementation**

- In execution suggestion prompt, include:
  - original user request (`self._user_request`)
  - completion title
  - bounded summary excerpt from `content`
  - explicit instruction to produce actionable follow-ups tied to this session output.
- Emit suggestion metadata (`source`, `anchor_event_id`, optional `anchor_excerpt`) when suggestions are produced after final report/message.
- Keep deterministic fallback when LLM suggestion generation fails.

**Step 4: Run tests to verify they pass**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/unit/agents/test_execution_suggestions.py backend/tests/domain/services/flows/test_discuss.py
```
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/execution.py backend/app/domain/services/flows/discuss.py backend/tests/domain/services/flows/test_discuss.py backend/tests/unit/agents/test_execution_suggestions.py
git commit -m "feat: generate session-anchored follow-up suggestions after completion"
```

---

### Task 6: End-to-End Verification and Quality Gates

**Files:**
- Modify (if needed for assertions only): `backend/tests/interfaces/api/test_sse_streaming.py`
- Modify (if needed): `frontend/tests/pages/ChatPage.spec.ts`

**Step 1: Write failing E2E-ish verification tests**

- Add SSE stream assertion that `suggestion` event carries expected metadata shape.
- Add frontend assertion that suggestions render only after response settlement and clicking suggestion sends contextual follow-up payload.

**Step 2: Run test suites to verify fail first**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= backend/tests/interfaces/api/test_sse_streaming.py
```

Run:
```bash
cd frontend && bun run vitest frontend/tests/pages/ChatPage.spec.ts
```

**Step 3: Implement minimal glue/fixes**

- Adjust serializers/types as required to satisfy E2E contracts.
- Keep backward compatibility for clients without follow-up metadata.

**Step 4: Run full required checks**

Run:
```bash
cd frontend && bun run lint && bun run type-check
```

Run:
```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

Expected: All commands pass.

**Step 5: Commit**

```bash
git add backend/tests/interfaces/api/test_sse_streaming.py frontend/tests/pages/ChatPage.spec.ts
git commit -m "test: verify contextual follow-up suggestions end-to-end"
```

---

## Rollout Notes

- Keep the new `follow_up` request field optional.
- Preserve regex-based suggestion follow-up detection for old clients.
- Prefer metadata-based routing when both are present.
- Add observability counters during implementation:
  - `follow_up_context_applied_total`
  - `follow_up_context_missing_total`
  - `follow_up_fast_path_skipped_total`

## Acceptance Criteria

1. Suggestions appear after task completion as today, but are grounded in current session output.
2. Clicking a suggestion sends contextual follow-up metadata to backend.
3. Suggestion-click follow-ups bypass context-free fast-path routing.
4. Follow-up responses no longer lose reference for "this/that/it" in same-session usage.
5. Frontend + backend checks pass via required repo commands.
