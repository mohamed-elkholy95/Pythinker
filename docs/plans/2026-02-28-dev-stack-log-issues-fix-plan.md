# Dev Stack Log Issues Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove real operational failures/noise seen in Docker dev-stack monitoring by fixing root causes in backend and sandbox services.

**Architecture:** Fix root causes at service boundaries (startup model initialization, sandbox API contract parity, citation/integrity post-processing) and reduce false-positive severity in provider-level fallback paths. Keep behavior fail-safe while reducing avoidable warnings/errors.

**Tech Stack:** FastAPI, Beanie ODM, Pydantic v2, async Python services, pytest.

---

### Task 1: Fix Event Archival Startup Initialization + Failure Diagnostics

**Files:**
- Modify: `backend/app/core/lifespan.py`
- Test: `backend/tests/test_periodic_session_cleanup.py`

**Step 1: Write failing tests**
- Add a test that validates event archival failure logging includes exception class info when exception has empty string representation.
- Add a test that validates `AgentEventDocument` is part of Beanie initialization model set.

**Step 2: Run tests to verify failure**
- Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/test_periodic_session_cleanup.py -q`
- Expected: new tests fail.

**Step 3: Minimal implementation**
- Include `AgentEventDocument` in `init_beanie(document_models=[...])`.
- Improve periodic archival failure logging to include exception class + traceback-safe details.

**Step 4: Re-run tests**
- Same command as Step 2.
- Expected: pass.

### Task 2: Reduce False-Positive Error Severity for Expected Search Exhaustion

**Files:**
- Modify: `backend/app/infrastructure/external/search/base.py`
- Test: `backend/tests/infrastructure/external/search/test_search_language_filter.py`

**Step 1: Write failing tests**
- Add test: quota/exhaustion message logs at warning level, not error.
- Add test: unknown/true failures still log at error.

**Step 2: Run tests to verify failure**
- Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/search/test_search_language_filter.py -q`
- Expected: new tests fail.

**Step 3: Minimal implementation**
- Add deterministic severity classification in `_create_error_result` for transient/expected provider exhaustion cases.

**Step 4: Re-run tests**
- Same command as Step 2.
- Expected: pass.

### Task 3: Strengthen Citation/Delivery Integrity Auto-Repair Path

**Files:**
- Modify: `backend/app/domain/services/agents/citation_integrity.py`
- Modify: `backend/app/domain/services/agents/execution.py`
- Test: `backend/tests/domain/services/agents/test_citation_integrity.py`
- Test: `backend/tests/unit/agents/test_execution_suggestions.py`

**Step 1: Write failing tests**
- Add citation test for pruning phantom references.
- Add execution test that substantial truncated output is auto-repaired/delivered without hard failure.

**Step 2: Run tests to verify failure**
- Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_citation_integrity.py tests/unit/agents/test_execution_suggestions.py -q`
- Expected: new tests fail.

**Step 3: Minimal implementation**
- Add phantom-reference pruning helper in citation integrity module.
- In summarize flow, attempt citation auto-repair before emitting unresolved warnings.
- Pre-apply truncation fallback note for substantial content before strict gate hard-block.

**Step 4: Re-run tests**
- Same command as Step 2.
- Expected: pass.

### Task 4: Implement Missing Sandbox File API Endpoints (`/file/delete`, `/file/list`)

**Files:**
- Modify: `sandbox/app/schemas/file.py`
- Modify: `sandbox/app/models/file.py`
- Modify: `sandbox/app/services/file.py`
- Modify: `sandbox/app/api/v1/file.py`
- Test: `sandbox/tests/test_api_file.py`
- Test: `sandbox/tests/test_service_path_normalization.py`

**Step 1: Write failing tests**
- Add API tests for `/api/v1/file/delete` and `/api/v1/file/list` happy paths and 404 behavior.
- Add path-traversal tests for the new service methods.

**Step 2: Run tests to verify failure**
- Run: `cd sandbox && pytest tests/test_api_file.py tests/test_service_path_normalization.py -q`
- Expected: new tests fail.

**Step 3: Minimal implementation**
- Add request/response models.
- Add service methods for secure delete and directory listing.
- Add API routes exposing those methods.

**Step 4: Re-run tests**
- Same command as Step 2.
- Expected: pass.

### Task 5: End-to-End Verification

**Files:**
- No code changes expected.

**Step 1: Run backend focused suite**
- Run: `conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/test_periodic_session_cleanup.py tests/infrastructure/external/search/test_search_language_filter.py tests/domain/services/agents/test_citation_integrity.py tests/unit/agents/test_execution_suggestions.py -q`

**Step 2: Run sandbox focused suite**
- Run: `cd sandbox && pytest tests/test_api_file.py tests/test_service_path_normalization.py -q`

**Step 3: Validate in live dev stack logs**
- Run Docker MCP checks for backend + sandbox logs and verify:
  - no `Periodic event archival failed` from `CollectionWasNotInitialized`
  - no `/api/v1/file/delete` or `/api/v1/file/list` 404 from sandbox
  - no hard `Delivery integrity gate blocked output` on substantial truncation-repairable responses

