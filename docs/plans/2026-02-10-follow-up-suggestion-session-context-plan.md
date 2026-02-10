# Follow-up Suggestion Session-Context Plan

Date: 2026-02-10
Owner: Backend + Frontend
Status: Investigation complete, implementation pending

## Problem Summary

In the same chat session, clicking a follow-up suggestion like:
- "Can you explain this in more detail?"

can produce a response that asks what "this" refers to, even though the previous assistant response is visible in the same chat.

## Investigation Findings

### 1. Frontend fallback suggestions are generic and ambiguous
- `frontend/src/pages/ChatPage.vue:1126` generates `"Can you explain this in more detail?"`.
- The screenshot text matches this fallback exactly, which indicates these suggestions likely came from frontend fallback, not backend contextual generation.

### 2. Suggestion click sends only plain text (no anchor context)
- `frontend/src/pages/ChatPage.vue:1291` sets input to selected suggestion and submits.
- No metadata is sent about which assistant message the suggestion came from.

### 3. AGENT fast-path can treat follow-up as standalone knowledge query
- `backend/app/domain/services/flows/fast_path.py:159` includes broad knowledge patterns (including `?` ending).
- `backend/app/domain/services/flows/fast_path.py:622` `execute_fast_knowledge()` calls LLM with only system + current question.
- `backend/app/domain/services/flows/plan_act.py:1691` executes fast-path and returns early, bypassing full session-aware workflow.

### 4. Intent classification follow-up handling is narrow
- `backend/app/domain/services/agents/intent_classifier.py:361` continuation phrases are limited to very short commands like "do it", "continue".
- "Can you explain this in more detail?" is not treated as continuation reliably.

### 5. Discuss prompt does not explicitly include prior session turns
- `backend/app/domain/services/flows/discuss.py:233` builds prompt from only current message + attachments.
- `backend/app/domain/services/prompts/discuss.py:57` prompt template includes only `User: {message}`.

### 6. Agent memories are role-scoped (discuss/planner/execution)
- `backend/app/domain/services/flows/discuss.py:60` agent memory name = `discuss`
- `backend/app/domain/services/agents/planner.py:157` memory name = `planner`
- `backend/app/domain/services/agents/execution.py:71` memory name = `execution`
- `backend/app/domain/services/agents/base.py:1073` memory persisted by `(agent_id, name)`

This means cross-flow context continuity is not guaranteed unless session history is explicitly injected.

## Enhancement Plan

## Phase 1 (Quick Win, Low Risk)

### 1. Improve fallback suggestion wording (frontend)
- Replace ambiguous fallback phrasing in `frontend/src/pages/ChatPage.vue`.
- Example replacements:
  - "Can you explain your previous answer in more detail?"
  - "What are the best next steps based on your last result?"
  - "Can you give a practical example based on your previous output?"

### 2. Fast-path guard for ambiguous follow-ups (backend)
- In `PlanActFlow` before fast-path execution, detect likely referential follow-up:
  - contains pronouns (`this/that/it/these/those`)
  - session has recent assistant message
- Skip `KNOWLEDGE` fast-path for those messages and continue with full flow.

Expected impact:
- Immediate reduction in "what does this refer to?" failures without protocol changes.

## Phase 2 (Core Fix: Session-anchored follow-up context)

### 1. Extend suggestion payload with provenance
- Add optional metadata to suggestion events:
  - `anchor_event_id`
  - `anchor_message_excerpt`
  - `source` (`backend_generated` | `frontend_fallback`)
- Touch points:
  - `backend/app/domain/models/event.py` (`SuggestionEvent`)
  - `backend/app/interfaces/schemas/event.py`
  - `frontend/src/types/event.ts`

### 2. Extend chat request contract with follow-up context
- Add optional `follow_up` object to chat request:
  - `selected_suggestion`
  - `anchor_event_id`
  - `anchor_excerpt`
  - `source`
- Touch points:
  - `backend/app/interfaces/schemas/session.py` (`ChatRequest`)
  - `frontend/src/api/agent.ts`
  - `frontend/src/pages/ChatPage.vue` (`handleSuggestionSelect`)

### 3. Resolve follow-up context server-side
- In `agent_domain_service.chat`, when `follow_up` exists:
  - load referenced assistant event from session history
  - build a resolved context string for routing/flow:
    - "User clicked follow-up to assistant reply: <excerpt>. Follow-up: <text>"
- Ensure this context is available to:
  - intent classification
  - fast-path routing
  - discuss/agent prompts

Expected impact:
- Follow-up clicks become deterministic and session-grounded.

## Phase 3 (Flow consistency and routing robustness)

### 1. Strengthen follow-up intent classification
- Update `IntentClassifier.classify_with_context` to treat suggestion-click follow-ups as continuation intent when prior mode was AGENT.
- Expand continuation phrase detection for common suggestion templates.

### 2. Discuss flow session-context injection
- Add recent session turns (last N user/assistant messages) to discuss prompt builder.
- Keep bounded context window to avoid prompt bloat.

Expected impact:
- Even if message routes to discuss, "this" references resolve correctly.

## Phase 4 (Validation + observability)

### Backend tests
- `backend/tests/test_fast_path.py`
  - Add coverage: pronoun-based follow-up should not use context-free `KNOWLEDGE` fast-path when anchor/session context exists.
- `backend/tests/test_intent_classifier.py`
  - Add coverage: suggestion-click follow-ups stay in AGENT continuation path.
- `backend/tests/domain/services/flows/test_discuss.py`
  - Add coverage: discuss prompt includes recent context turns.

### Frontend tests
- Add tests for suggestion click payload construction (anchor metadata included).
- Add tests that fallback suggestion text is explicit (non-ambiguous referents).

### Metrics/logging
- Add counters:
  - `follow_up_context_applied_total`
  - `follow_up_context_missing_total`
  - `follow_up_fast_path_skipped_total`

## Acceptance Criteria

1. Clicking a suggestion in the same session that contains "this/that/it" resolves against previous assistant output without asking what it refers to.
2. Fast-path no longer handles ambiguous referential follow-ups without contextual anchor.
3. Suggestion-click requests carry provenance metadata end-to-end.
4. New tests cover routing + context injection path and pass in CI.

## Rollout Strategy

1. Ship Phase 1 behind no flag (safe text/routing guard).
2. Ship Phase 2+3 behind a feature flag (e.g. `follow_up_context_v2`) for incremental rollout.
3. Monitor counters and sample logs for context-miss regressions.

