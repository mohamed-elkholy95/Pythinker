# Deep Research Reliability Enhancement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the context-cap recovery loop, make summarization consume explicit compact context, stop report-verification shell thrash, and harden chart generation for deep-research sessions like `a978bf17ea84430a`.

**Architecture:** Treat deep-research reliability as a pipeline problem instead of a single cap-tuning problem. The flow should shrink context before summarization, carry deliverables and artifacts through explicit summarize-time state instead of late `system_prompt` mutation, reduce search payloads before they enter memory, and only perform shell/chart work when the runtime can support it.

**Tech Stack:** Python 3.12, FastAPI/LangGraph backend, asyncio, Pydantic v2, pytest, Ruff, Docker sandbox, docker-compose

---

## File Map

- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/domain/services/agents/execution.py`
- Modify: `backend/app/domain/services/agents/base.py`
- Modify: `backend/app/domain/services/agents/context_compression_pipeline.py`
- Modify: `backend/app/domain/services/tools/search.py`
- Modify: `backend/app/core/config_scraping.py`
- Modify: `backend/app/core/config_features.py`
- Modify: `backend/app/domain/services/prompts/execution.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/domain/services/plotly_chart_orchestrator.py`
- Modify: `backend/app/core/prometheus_metrics.py`
- Modify: `sandbox/Dockerfile`
- Modify: `docker-compose.yml`
- Create: `backend/tests/domain/services/flows/test_plan_act_summarization_context.py`
- Create: `backend/tests/domain/services/tools/test_search_preview_budget.py`
- Create: `backend/tests/domain/services/prompts/test_report_workflow_prompt.py`
- Create: `backend/tests/domain/services/test_plotly_runtime_fallback.py`
- Modify: `backend/tests/domain/services/agents/test_graduated_compaction.py`
- Modify: `backend/tests/domain/services/agents/test_truncation_recovery_fixes.py`
- Modify: `backend/tests/domain/services/flows/test_verification_hallucination_fix.py`
- Modify: `backend/tests/unit/agents/test_report_quality_pipeline.py`
- Modify: `backend/tests/domain/services/tools/test_search_auto_enrich.py`
- Modify: `backend/tests/domain/services/test_report_file_attachment.py`
- Modify: `backend/tests/domain/services/test_llm_chart_analysis.py`
- Modify: `backend/tests/unit/core/test_config_scraping.py`
- Modify: `backend/README.md`
- Modify: `backend/CLAUDE.md`

## Chunk 1: Summarization handoff and context reset

### Task 1: Capture the summarize-time context bug with TDD

**Files:**
- Create: `backend/tests/domain/services/flows/test_plan_act_summarization_context.py`
- Modify: `backend/tests/unit/agents/test_report_quality_pipeline.py`

- [ ] Add a regression test that seeds executor memory, mutates `executor.system_prompt` after memory exists, and proves the added text does not reach the live summarize message list today.
- [ ] Add a regression test that expects workspace deliverables and artifact-manifest text to appear in the actual summarize-time prompt payload once the fix lands.
- [ ] Run: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/flows/test_plan_act_summarization_context.py tests/unit/agents/test_report_quality_pipeline.py`
- [ ] Confirm the failures are on the intended assertions before touching implementation.

### Task 2: Add an explicit pre-summarization handoff path

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/domain/services/agents/execution.py`
- Modify: `backend/app/domain/services/agents/base.py`
- Modify: `backend/app/domain/services/agents/context_compression_pipeline.py`

- [ ] Add one `PlanActFlow` helper that runs immediately before `AgentStatus.SUMMARIZING` and compacts memory to a defined target using one path instead of scattered ad hoc truncation.
- [ ] Replace late `self.executor.system_prompt += ...` summarize-time mutations with explicit summarize payload assembly that gets added to memory or passed directly into summarize prompt construction.
- [ ] Make `ExecutionAgent.summarize()` accept and consume that explicit payload while keeping `artifact_references` as the attachment source of truth.
- [ ] Re-run: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/flows/test_plan_act_summarization_context.py tests/unit/agents/test_report_quality_pipeline.py tests/domain/services/agents/test_graduated_compaction.py tests/domain/services/agents/test_truncation_recovery_fixes.py tests/domain/services/flows/test_verification_hallucination_fix.py`

### Task 3: Surface cap behavior and handoff outcomes

**Files:**
- Modify: `backend/app/domain/services/agents/base.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`
- Modify: `backend/app/core/prometheus_metrics.py`

- [ ] Add counters/histograms for hard-cap hits, forced step advancement, and pre-summarization compression outcomes.
- [ ] Log the effective deep-research cap at flow start so the runtime value is visible even when it differs from the code default.
- [ ] Add focused metrics tests if none exist; otherwise extend the nearest existing observability test module.
- [ ] Re-run the targeted backend pytest command for the touched metrics tests.

## Chunk 2: Search payload reduction before memory serialization

### Task 4: Write failing tests for deep-research search budgets

**Files:**
- Create: `backend/tests/domain/services/tools/test_search_preview_budget.py`
- Modify: `backend/tests/domain/services/tools/test_search_auto_enrich.py`
- Modify: `backend/tests/unit/core/test_config_scraping.py`

- [ ] Add tests proving deep-research mode can use stricter search enrichment and background-preview budgets than generic flows.
- [ ] Add tests proving search payload serialization keeps only the configured number of results in LLM memory while full payloads remain offloaded or summarized.
- [ ] Run: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_search_preview_budget.py tests/domain/services/tools/test_search_auto_enrich.py tests/unit/core/test_config_scraping.py`
- [ ] Verify the failures clearly point to missing mode-aware budgeting behavior.

### Task 5: Implement mode-aware search/result compaction

**Files:**
- Modify: `backend/app/domain/services/tools/search.py`
- Modify: `backend/app/domain/services/agents/base.py`
- Modify: `backend/app/core/config_scraping.py`
- Modify: `backend/app/core/config_features.py`
- Modify: `backend/app/domain/services/agents/tool_result_store.py`

- [ ] Add explicit deep-research knobs or mode-aware branches for `search_auto_enrich_top_k`, `search_auto_enrich_snippet_chars`, `browser_background_preview_count`, and preview dwell time.
- [ ] Reduce memory pressure by preferring structured summaries and `ToolResultStore` references over enriched raw snippets in conversation memory.
- [ ] Keep default behavior unchanged for non-research flows unless the new config explicitly says otherwise.
- [ ] Re-run: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/tools/test_search_preview_budget.py tests/domain/services/tools/test_search_auto_enrich.py tests/unit/core/test_config_scraping.py tests/domain/services/agents/test_tool_result_store.py tests/domain/services/agents/test_graduated_compaction.py`

## Chunk 3: Report verification stability and filename discipline

### Task 6: Capture shell-verification thrash with TDD

**Files:**
- Create: `backend/tests/domain/services/prompts/test_report_workflow_prompt.py`
- Modify: `backend/tests/domain/services/test_report_file_attachment.py`

- [ ] Add tests proving the deliverable workflow prompt points verification at the actual file path or tracked attachment, not a generic example like `report.md`.
- [ ] Add tests proving a failed verification attempt does not trigger repeated filename guessing once a markdown attachment already exists.
- [ ] Run: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/prompts/test_report_workflow_prompt.py tests/domain/services/test_report_file_attachment.py`
- [ ] Confirm the failures match the `report.md` example path and retry-loop assumptions.

### Task 7: Make verification path-exact and loop-resistant

**Files:**
- Modify: `backend/app/domain/services/prompts/execution.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/domain/services/flows/plan_act.py`

- [ ] Rewrite the deliverable workflow prompt so shell verification is conditional, uses the actual saved path, and does not encourage directory listing churn when `file_write` already succeeded.
- [ ] Add a runner-side or flow-side guard that suppresses repeated verification attempts after the first miss when the report attachment is already tracked.
- [ ] Normalize attachment filename matching so basename and canonical `report-{id}.md` references resolve to one logical report.
- [ ] Re-run: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/prompts/test_report_workflow_prompt.py tests/domain/services/test_report_file_attachment.py tests/unit/agents/test_report_quality_pipeline.py`

## Chunk 4: Plotly runtime hardening

### Task 8: Write failing tests for Plotly capability detection

**Files:**
- Create: `backend/tests/domain/services/test_plotly_runtime_fallback.py`
- Modify: `backend/tests/domain/services/test_llm_chart_analysis.py`
- Modify: `backend/tests/domain/services/test_report_file_attachment.py`

- [ ] Add tests that simulate Plotly enabled but unavailable in the sandbox and expect immediate structured fallback to SVG without noisy repeated subprocess behavior.
- [ ] Add tests that simulate Plotly available and expect normal HTML and PNG attachment creation.
- [ ] Run: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_plotly_runtime_fallback.py tests/domain/services/test_llm_chart_analysis.py tests/domain/services/test_report_file_attachment.py`
- [ ] Verify the failures distinguish missing runtime capability from normal SVG fallback behavior.

### Task 9: Enforce one supported Plotly deployment story

**Files:**
- Modify: `backend/app/domain/services/plotly_chart_orchestrator.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `sandbox/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] Add a cheap capability check before launching the Plotly script; if unavailable, return a typed “plotly unavailable” reason that the runner maps directly to legacy SVG fallback.
- [ ] Decide the deployment policy and encode it in config/runtime wiring: either enable sandbox addons where Plotly is enabled, or default Plotly off until addons are present.
- [ ] If the deployment policy changes, update the compose file and sandbox image path so local/dev runtime matches backend feature flags.
- [ ] Re-run: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_plotly_runtime_fallback.py tests/domain/services/test_llm_chart_analysis.py tests/domain/services/test_report_file_attachment.py`

## Chunk 5: End-to-end verification and docs

### Task 10: Run targeted backend verification

- [ ] Run lint: `cd backend && ruff check .`
- [ ] Run format check: `cd backend && ruff format --check .`
- [ ] Run targeted tests: `cd backend && pytest -p no:cov -o addopts= tests/domain/services/flows/test_plan_act_summarization_context.py tests/unit/agents/test_report_quality_pipeline.py tests/domain/services/agents/test_graduated_compaction.py tests/domain/services/agents/test_truncation_recovery_fixes.py tests/domain/services/flows/test_verification_hallucination_fix.py tests/domain/services/tools/test_search_preview_budget.py tests/domain/services/tools/test_search_auto_enrich.py tests/domain/services/prompts/test_report_workflow_prompt.py tests/domain/services/test_report_file_attachment.py tests/domain/services/test_plotly_runtime_fallback.py tests/domain/services/test_llm_chart_analysis.py tests/unit/core/test_config_scraping.py`
- [ ] Do not run the full backend suite unless a targeted failure proves it is necessary.

### Task 11: Run a live smoke session and inspect logs

- [ ] Start the relevant services with Docker CLI and trigger one deep-research comparison run that should produce a markdown report and chart output.
- [ ] Check backend logs: `docker logs pythinker-backend-1 --since 15m 2>&1 | rg "Hard context cap hit|stuck_recovery_exhausted|Plotly script reported failure|grounding verification timed out"`
- [ ] Check sandbox logs: `docker logs pythinker-sandbox-1 --since 15m 2>&1 | rg "return code: 1|No module named 'plotly'"`
- [ ] Expected: no `stuck_recovery_exhausted`, no repeated verification-probe failures, and no Plotly import failure when the feature is enabled.

### Task 12: Refresh docs for the new runtime contract

**Files:**
- Modify: `backend/README.md`
- Modify: `backend/CLAUDE.md`

- [ ] Document the new summarize-time context handoff, deep-research search-budget knobs, and Plotly deployment/fallback policy.
- [ ] Keep the docs aligned with the final runtime behavior instead of the pre-fix architecture.

## Success Criteria

- A deep-research comparison run no longer force-advances through `stuck_recovery_exhausted`.
- Summarization consumes explicit compact context rather than late `system_prompt` mutations.
- Search enrichment and background preview no longer flood memory before writing begins.
- Report verification does not guess alternate filenames after a successful `file_write`.
- Plotly either works cleanly when enabled or falls back cleanly when unavailable.
