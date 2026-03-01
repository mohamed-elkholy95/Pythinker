# Research Session Stability Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent false failed sessions after interruption/reload, improve timeout resilience for tool-enabled LLM calls, and return accurate zero-progress research failure reasons.

**Architecture:** Keep existing flow/task architecture and patch only failure-path decision points. Add targeted unit tests first, then minimal code updates in `AgentDomainService`, `PlanActFlow`, and `OpenAILLM` to preserve behavior outside the failing paths.

**Tech Stack:** Python 3.11, asyncio, pytest, FastAPI domain services, OpenAI-compatible LLM adapter.

---

### Task 1: Orphaned RUNNING Session Recovery

**Files:**
- Modify: `backend/tests/domain/services/test_agent_domain_service_chat_teardown.py`
- Modify: `backend/app/domain/services/agent_domain_service.py`

**Step 1: Write the failing test**
- Update orphaned session test to expect `CANCELLED` teardown status and cancellation-oriented error wording.

**Step 2: Run test to verify it fails**
- Run: `conda run -n pythinker pytest -p no:cov -o addopts= backend/tests/domain/services/test_agent_domain_service_chat_teardown.py::test_chat_no_active_task_and_running_session_emits_error_and_tears_down`
- Expected: FAIL with status mismatch (`FAILED` vs `CANCELLED`).

**Step 3: Write minimal implementation**
- In orphaned `RUNNING` + no active task branch, mark `CANCELLED` instead of `FAILED`.
- Emit/persist clear interruption message indicating task interruption and retry guidance.

**Step 4: Run test to verify it passes**
- Re-run the same test.

### Task 2: Zero-Progress Error Reasoning

**Files:**
- Modify: `backend/tests/domain/services/flows/test_verification_hallucination_fix.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`

**Step 1: Write the failing test**
- Add tests for helper that builds zero-progress error message:
  - timeout in failed step -> timeout-specific reason
  - blocked-only path -> dependency-blocked reason
  - default path -> generic reason

**Step 2: Run tests to verify they fail**
- Run: `conda run -n pythinker pytest -p no:cov -o addopts= backend/tests/domain/services/flows/test_verification_hallucination_fix.py -k "zero_progress"`

**Step 3: Write minimal implementation**
- Add helper in `PlanActFlow` to derive reason from failed/blocked step metadata.
- Use helper in summarizing gate ErrorEvent string.

**Step 4: Run tests to verify they pass**
- Re-run same targeted tests.

### Task 3: Adaptive Tool-Call Timeout Retry

**Files:**
- Modify: `backend/tests/infrastructure/external/llm/test_openai_llm_tool_call_guards.py`
- Modify: `backend/app/infrastructure/external/llm/openai_llm.py`

**Step 1: Write the failing test**
- Add test asserting second tool-timeout retry uses larger timeout budget (capped by `llm_request_timeout`).

**Step 2: Run test to verify it fails**
- Run: `conda run -n pythinker pytest -p no:cov -o addopts= backend/tests/infrastructure/external/llm/test_openai_llm_tool_call_guards.py -k "backoff"`

**Step 3: Write minimal implementation**
- For tool-enabled calls, compute per-attempt timeout with exponential backoff from `llm_tool_request_timeout`, capped at `llm_request_timeout`.
- Keep existing retry/fallback model behavior intact.

**Step 4: Run test to verify it passes**
- Re-run same targeted tests.

### Task 4: Focused Regression Verification

**Files:**
- No code changes expected.

**Step 1: Run impacted suites**
- `conda run -n pythinker pytest -p no:cov -o addopts= backend/tests/domain/services/test_agent_domain_service_chat_teardown.py`
- `conda run -n pythinker pytest -p no:cov -o addopts= backend/tests/domain/services/flows/test_verification_hallucination_fix.py`
- `conda run -n pythinker pytest -p no:cov -o addopts= backend/tests/infrastructure/external/llm/test_openai_llm_tool_call_guards.py`

**Step 2: Summarize outcomes**
- Record passing/failing status and any residual risks.
