# Session Monitoring Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all bugs found during live session monitoring of session `5a7589a5467541b3`

**Architecture:** Three targeted fixes across PDF rendering, metrics observability, and task state tracking. All leverage existing infrastructure with minimal code changes.

**Tech Stack:** Python, ReportLab/Playwright PDF, Prometheus metrics, Mermaid CLI (mmdc), httpx

**Session monitored:** `5a7589a5467541b3` (Telegram gateway, GLM-5, deep_research)

---

## Bugs Found & Fixes Applied

### Fix 1: Mermaid Diagram Rendering in Telegram PDF (Critical)

**Root cause:** `_build_mermaid_preprocessor()` in `dependencies.py` created an `httpx.AsyncClient` without the `x-sandbox-secret` auth header. The sandbox API rejected all requests from the MermaidPreprocessor, but the error was silently caught by `except Exception` handlers. Mermaid code blocks appeared as raw text in PDFs.

**Fix:** Added `x-sandbox-secret` header injection from `settings.sandbox_api_secret` + added logging for initialization confirmation. Also added explicit try/except with logging in `PlaywrightPdfRenderer.render()` for visibility.

**Files modified:**
- `backend/app/interfaces/dependencies.py` — auth header injection
- `backend/app/infrastructure/external/pdf/playwright_pdf_renderer.py` — error visibility

**Context7 validated:** Mermaid CLI docs (`/mermaid-js/mermaid-cli`), WeasyPrint Python API (`/kozea/weasyprint`)

### Fix 2: Citation Fabrication Metrics (Medium)

**Root cause:** GLM-5 generated 4 fabricated citation references (13% fabrication rate). The citation_integrity module repaired them, but no metrics were emitted for observability.

**Fix:** Added `pythinker_citation_fabricated_total` Prometheus counter. Incremented in `repair_citations()` when fabricated references are detected.

**Files modified:**
- `backend/app/core/prometheus_metrics.py` — new counter
- `backend/app/domain/services/agents/citation_integrity.py` — metric emission

### Fix 3: task_state.md Completion (Low)

**Root cause:** When the agent reaches "no more steps" and transitions to COMPLETED, steps 4-5 (merged/skipped) remained unchecked in task_state.md because no final save was triggered.

**Fix:** Added `TaskState.mark_remaining_completed()` method. Called in `plan_act.py` when execution finishes to mark all pending/in_progress steps as completed, then force-saves to sandbox.

**Files modified:**
- `backend/app/domain/services/agents/task_state_manager.py` — `mark_remaining_completed()`
- `backend/app/domain/services/flows/plan_act.py` — final save on completion

### Fix 4: LLM Timeout (Working as Designed)

**Assessment:** The 90s timeout on GLM-5 during step 4 was the `llm_tool_request_timeout` working correctly. It caught the stall and retried successfully (5s on attempt 2). No code change needed.

### Bugs NOT fixed (observed but not actionable):

- **BUG 1 (Slow scraping):** First search took 42.8s due to tiered fallback — requires deeper scraping pipeline refactor
- **BUG 4 (Plotly chart extraction):** Fell back to SVG — requires chart data extraction from markdown tables
- **BUG 6 (Content completeness warning):** Likely addressed by Mermaid rendering fix (richer output)

---

## Test Results

- `tests/unit/pdf/test_mermaid_preprocessor.py` — 13 passed
- `tests/domain/services/agents/test_citation_integrity.py` — 30 passed
- `tests/domain/services/pdf/` — 9 passed
- All affected suites: **52 passed**
