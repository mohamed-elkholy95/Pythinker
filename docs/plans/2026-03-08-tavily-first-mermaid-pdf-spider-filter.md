# Tavily-First / Mermaid / PDF Spider Filter Delta Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` if additional follow-up implementation is requested from this document.

**Goal:** Align the current search and PDF stack with the already-landed Tavily-first architecture, remove redundant work from the plan, and harden the remaining gaps validated against Context7 documentation.

**Architecture:** Keep the existing Tavily-first provider policy, Mermaid preprocessing, and PDF URL spider filtering. Apply only delta changes that improve correctness, renderer parity, sandbox reliability, and regression coverage.

**Context7 validation used for this plan:**
- Tavily Search supports native `time_range` values `day`, `week`, `month`, `year`.
- Mermaid CLI supports `--puppeteerConfigFile` and custom `executablePath` for containerized Chromium environments.

---

## Execution Status (2026-03-08)

- **Task 1 (repo audit and redundancy removal): Completed**
- **Task 2 (Tavily native request alignment): Completed**
- **Task 3 (Mermaid sandbox runtime hardening): Completed**
- **Task 4 (Playwright Mermaid rendering parity): Completed**
- **Task 5 (ReportLab and factory regression coverage): Completed**
- **Task 6 (PDF spider skip regression coverage): Completed**
- **Task 7 (repo-wide verification and merge): In Progress**

---

## What Was Already Present

The original plan needed to be reduced to a delta because these capabilities already existed in the codebase:

1. Tavily-first provider policy already exists in `backend/app/core/search_provider_policy.py`.
2. Mermaid preprocessing already exists for the ReportLab path.
3. PDF spider URL filtering already exists in `backend/app/domain/services/tools/search.py`.
4. ReportLab is already wired as the safe PDF fallback.

The plan should therefore not re-implement those features. It should only close the remaining correctness and verification gaps.

---

## Delta Tasks

### Task 1: Audit current implementation and remove redundant work

**Status:** Completed

**Outcome:**
- Confirmed Tavily-first policy already exists.
- Confirmed Mermaid preprocessing already exists for ReportLab.
- Confirmed PDF URL filtering already exists before spider enrichment.
- Reduced the plan scope to hardening and regression coverage instead of reimplementation.

### Task 2: Align Tavily requests with native API semantics

**Status:** Completed

**Files:**
- `backend/app/infrastructure/external/search/tavily_search.py`
- `backend/tests/infrastructure/external/search/test_tavily_search.py`

**Changes:**
1. Map internal date ranges to Tavily-native `time_range` values.
2. Preserve the original query text instead of appending date hints.
3. Add regression coverage for supported and unsupported ranges.

**Context7 basis:**
- Tavily Search accepts `time_range` directly, so date-hint mutation in `query` is unnecessary and less precise.

### Task 3: Harden Mermaid CLI usage in the sandbox image

**Status:** Completed

**Files:**
- `sandbox/Dockerfile`

**Changes:**
1. Pin Mermaid CLI explicitly in the image.
2. Keep a single global installation path for Mermaid CLI.
3. Copy the Puppeteer config into the runtime stage.
4. Configure Mermaid CLI with:
   - `executablePath=/usr/bin/chromium-browser`
   - `--no-sandbox`
   - `--disable-setuid-sandbox`
5. Validate by rendering a real Mermaid diagram in the runtime image.

**Context7 basis:**
- Mermaid CLI supports a Puppeteer config file and a custom `executablePath` for already-installed Chromium.

### Task 4: Give the Playwright PDF renderer Mermaid parity

**Status:** Completed

**Files:**
- `backend/app/infrastructure/external/pdf/playwright_pdf_renderer.py`
- `backend/app/interfaces/dependencies.py`
- `backend/tests/infrastructure/external/pdf/test_playwright_pdf_renderer.py`

**Changes:**
1. Wire `sandbox_base_url` into the Playwright renderer.
2. Reuse `MermaidPreprocessor` before HTML normalization.
3. Replace Mermaid placeholders with inline base64 PNG markdown images.
4. Preserve existing fallback behavior to ReportLab.

### Task 5: Add the missing regression coverage around renderer wiring

**Status:** Completed

**Files:**
- `backend/tests/domain/services/pdf/test_reportlab_pdf_renderer.py`
- `backend/tests/interfaces/test_pdf_renderer_factory.py`
- `backend/tests/domain/utils/test_markdown_to_pdf.py`

**Changes:**
1. Verify ReportLab forwards Mermaid placeholders and rendered images correctly.
2. Verify the renderer factory normalizes sandbox address wiring for both ReportLab and Playwright.
3. Verify markdown-to-flowables turns Mermaid placeholders into image flowables.

### Task 6: Prove spider enrichment skips PDFs before fetch

**Status:** Completed

**Files:**
- `backend/tests/domain/services/tools/test_search_budget.py`

**Changes:**
1. Add a behavior-level regression test proving spider enrichment excludes PDF URLs before `fetch_batch`.

### Task 7: Complete repo-wide verification before merge

**Status:** In Progress

**Required verification gates:**
1. Backend: `ruff check .`
2. Backend: `ruff format --check .`
3. Backend: `pytest tests/`
4. Frontend: `bun run lint:check`
5. Frontend: `bun run type-check`
6. Frontend: `bun run test:run`
7. Sandbox: Mermaid CLI runtime smoke render

This task is only complete once the branch is verified and merged without changing the tested tree.

---

## Acceptance Criteria

1. Tavily requests use native `time_range` when supported and leave `query` unchanged.
2. Mermaid rendering works in both ReportLab and Playwright PDF flows when sandbox access is available.
3. Mermaid CLI renders successfully inside the runtime sandbox image.
4. Spider enrichment does not attempt to fetch PDF URLs.
5. Renderer wiring is covered by regression tests.
6. Repo-level verification passes before merge.

---

## Notes

- This is a delta plan, not a from-scratch implementation plan.
- Existing behavior was intentionally reused instead of duplicated.
- Final status must remain factual: no task should be marked completed without fresh verification evidence.
