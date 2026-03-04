# Telegram PDF Design-Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver automatic Telegram report PDFs that match the existing Tiptap report modal design (typography, spacing, tables, inline citations, references) with no citation/reference discrepancies.

**Architecture:** Introduce a renderer abstraction in domain services, implement a Chromium/Playwright HTML renderer as the primary path for design parity, and keep ReportLab as a fallback for resiliency. Reuse the report modal’s normalization + citation conventions as a shared contract so UI and PDF output stay consistent.

**Tech Stack:** Python 3.12, Playwright (Chromium), existing Telegram delivery policy, optional Jinja2 template rendering, existing ReportLab fallback, pytest + pypdf.

---

## Execution Status (2026-03-04)

- **Task 1 (regression-first parity tests): Completed**
- **Task 2 (domain renderer abstraction): Completed**
- **Task 3 (citation-normalization parity module): Completed**
- **Task 4 (modal-parity HTML/CSS bundle): Completed**
- **Task 5 (Playwright renderer primary path): Completed**
- **Task 6 (ReportLab fallback hardening): Completed**
- **Task 7 (end-to-end parity verification): Completed**
- **Task 8 (operational safeguards and observability): Completed**
  - Completed: renderer selection config, fallback wiring, integration contract coverage.
  - Completed: renderer-type/failure-reason + citation-integrity metrics expansion in `prometheus_metrics.py`.

### Additional hardening completed after initial plan

- **CI contract enforcement: Completed**
  - Workflow now installs Playwright Chromium and `poppler-utils`, and runs Telegram PDF integration contract on push and PR.
- **Visual regression guard: Completed**
  - Added first-page pHash visual baseline contract with deterministic fixture timestamps and citation/reference anchor assertions.
- **Baseline regeneration tooling: Completed**
  - Added script to regenerate visual baseline fixture from current renderer/template output.

---

## Scope and Evidence (Completed Analysis)

### Observed problems in current Telegram PDF output

1. **Layout does not match report modal design**
- Current pipeline uses ReportLab flowables, not modal CSS/structure.
- File: `backend/app/domain/utils/markdown_to_pdf.py`.

2. **Table rendering defects and clipping**
- Tables are created as plain string cells without width control or wrapped Paragraph cells.
- This causes clipped columns in long rows.
- Code path: `Table(rows, repeatRows=1)` with no `colWidths` and string cell content.
- File: `backend/app/domain/utils/markdown_to_pdf.py:195-211` and `:397-415`.

3. **Duplicate References sections**
- References are often already present in markdown content and then appended again from structured `sources`.
- Code path appends `PageBreak() + "References"` unconditionally when `sources` exists.
- File: `backend/app/domain/utils/markdown_to_pdf.py:318-330`.

4. **TOC/pagination noise for chat-delivered PDFs**
- Auto-TOC includes too many entries and consumes extra pages for Telegram reports.
- File: `backend/app/domain/utils/markdown_to_pdf.py:267-278` and `:305-315`.

5. **Unsupported glyphs (emoji/title symbols)**
- Missing emoji glyphs render as empty boxes in output.
- Font fallback currently selects Latin-focused fonts, not emoji-capable fonts.
- File: `backend/app/domain/utils/markdown_to_pdf.py:109-133`.

6. **Citation/reference parity mismatch with Tiptap modal**
- Frontend applies normalization/linkification and reference anchoring rules that backend PDF path does not apply.
- Files:
  - `frontend/src/components/report/reportContentNormalizer.ts:186-277`
  - `frontend/src/components/report/ReportModal.vue:1065-1133`
  - `backend/app/domain/services/channels/telegram_delivery_policy.py:316-323`

### Telegram and renderer constraints (validated)

- Telegram `sendMessage` text limit: 1-4096 chars.
- Telegram `sendDocument` caption limit: 0-1024 chars.
- Telegram upload max file size via Bot API: 50 MB.
- Sources:
  - https://core.telegram.org/bots/api#sendmessage
  - https://core.telegram.org/bots/api#senddocument

- Playwright `page.pdf()` supports A4, margins, print background, header/footer, CSS page size controls.
- Source:
  - https://github.com/microsoft/playwright/blob/main/docs/src/api/class-page.md

- ReportLab TOC requires `BaseDocTemplate.afterFlowable` + `multiBuild` pattern.
- Source:
  - https://docs.reportlab.com/reportlab/userguide/ch9_other_useful_flowables

---

## Library Decision Matrix

### Option A: Keep ReportLab and harden current parser

**Pros**
- Lowest migration risk.
- Already integrated in Telegram path.

**Cons**
- Hard to achieve exact parity with modal’s CSS-based look.
- Citation badge visual parity is impractical.
- Continued maintenance burden in markdown parser edge cases.

**Decision:** Good short-term stabilization, not enough for “same design as modal”.

### Option B: WeasyPrint renderer (HTML/CSS in Python)

**Pros**
- Strong paged-media CSS support.
- Python-native and deterministic.

**Cons**
- Not full browser engine; can diverge from frontend rendering behavior.
- Still requires a backend-specific HTML/CSS rendering contract.

**Decision:** Strong alternative if Chromium runtime is unacceptable.

### Option C: Playwright/Chromium renderer (Recommended)

**Pros**
- Best chance of matching modal design exactly.
- Full CSS rendering parity and stable PDF print controls.
- Already present in dependencies (`playwright>=1.48.0`).

**Cons**
- Browser runtime overhead and extra operational dependency.
- Requires robust timeout/fallback handling.

**Decision:** **Recommended primary renderer** for exact design + citation parity.

### Option D: xhtml2pdf/fpdf2 quick replacement

**Pros**
- Simpler APIs for basic documents.

**Cons**
- Limited modern CSS fidelity for modal-like design parity.
- Increased chance of formatting drift.

**Decision:** Not recommended for this requirement.

Sources:
- WeasyPrint docs: https://github.com/kozea/weasyprint/blob/main/README.rst
- WeasyPrint API support notes: https://github.com/kozea/weasyprint/blob/main/docs/api_reference.rst
- xhtml2pdf README/docs: https://github.com/xhtml2pdf/xhtml2pdf/blob/master/README.rst
- xhtml2pdf supported CSS reference: https://github.com/xhtml2pdf/xhtml2pdf/blob/master/docs/source/reference/html.rst

---

## Target Architecture

### 1) Renderer abstraction (Domain)

Create a domain contract for PDF generation:
- `PdfReportRenderer` interface with `render(report_payload) -> bytes`.
- Renderer selection by config (`playwright`, `reportlab`).

This keeps dependency direction clean:
- Domain depends on abstraction.
- Infrastructure provides implementations.
- Telegram delivery policy depends only on abstraction.

### 2) Shared report payload contract

Define a canonical payload used by UI and PDF:
- `title`
- `author`
- `generated_at`
- `markdown_content`
- `sources` (structured citations)
- `render_mode` (`telegram_pdf`)

### 3) Citation parity layer

Implement the same semantics currently used in frontend normalizer:
- inline citation detection `[N]`
- reference section normalization and numbering stabilization
- reference anchor generation (`#ref-N`)
- mismatch detection:
  - inline citation without reference
  - reference without source/url
  - duplicate numbering

### 4) HTML/CSS parity renderer (Playwright)

Generate print HTML that mirrors modal styles:
- typography, spacing, heading scales
- table style and page-break control
- inline citation badge style from modal (`a[href^="#ref-"]`)
- references section style (`.ref-list-anchor` equivalent)

Render using `page.setContent(...)` then `page.pdf(...)` with A4 and print background.

### 5) Fallback and reliability

If Playwright rendering fails:
- fallback to hardened ReportLab renderer
- emit structured metrics/logging for failure reason
- keep Telegram delivery contract unchanged

---

## Implementation Tasks

### Task 1: Add regression-first test harness for PDF parity

**Files:**
- Modify: `backend/tests/domain/services/channels/test_telegram_delivery_policy.py`
- Create: `backend/tests/domain/services/pdf/test_pdf_parity_contract.py`
- Create: `backend/tests/fixtures/reports/sample_modal_parity_report.md`

**Steps:**
1. Add failing test asserting generated PDF contains exactly one References section.
2. Add failing test asserting all inline `[N]` citations appear in references.
3. Add failing test asserting no clipped table text for long-cell fixture (text extract contains full header/cell tokens).
4. Add failing test asserting title sanitization removes unsupported glyphs from PDF metadata/title line.

### Task 2: Introduce domain renderer abstraction

**Files:**
- Create: `backend/app/domain/services/pdf/pdf_renderer.py`
- Create: `backend/app/domain/services/pdf/models.py`
- Modify: `backend/app/domain/services/channels/telegram_delivery_policy.py`

**Steps:**
1. Define `ReportPdfPayload` model and `PdfReportRenderer` protocol.
2. Inject renderer into `TelegramDeliveryPolicy` constructor.
3. Replace direct call to `build_pdf_bytes` with renderer invocation.
4. Keep backward compatibility by defaulting to existing ReportLab adapter.

### Task 3: Implement citation-normalization parity module

**Files:**
- Create: `backend/app/domain/services/pdf/markdown_normalizer.py`
- Create: `backend/tests/domain/services/pdf/test_markdown_normalizer.py`

**Steps:**
1. Port critical logic from frontend normalizer:
- reference heading detection
- `[N]` linkification behavior
- reference numbering normalization
- duplicate-title collapse safeguards
2. Add tests covering bracket refs, ordered refs, mixed refs, code fence exclusions.
3. Add validation result object (`missing_refs`, `orphan_refs`, `duplicate_refs`).

### Task 4: Build modal-parity HTML template and style bundle

**Files:**
- Create: `backend/app/infrastructure/external/pdf/templates/report_document.html`
- Create: `backend/app/infrastructure/external/pdf/styles/report_document.css`
- Modify: `frontend/src/components/report/ReportModal.vue` (extract reusable print-safe CSS tokens)

**Steps:**
1. Extract stable document-body styles into shareable CSS (headings, body, code, table, citation badge).
2. Reuse citation badge and references styling from modal export mode.
3. Keep Telegram-specific print layout (no modal header/actions/TOC sidebar chrome).
4. Add snapshot test for generated HTML skeleton.

### Task 5: Implement Playwright PDF renderer (primary)

**Files:**
- Create: `backend/app/infrastructure/external/pdf/playwright_pdf_renderer.py`
- Modify: `backend/app/core/config_channels.py`
- Modify: `backend/app/interfaces/gateway/gateway_runner.py`
- Modify: `backend/Dockerfile`

**Steps:**
1. Add renderer config:
- `telegram_pdf_renderer: Literal["playwright", "reportlab"] = "playwright"`
- render timeout and concurrency caps.
2. Implement async Playwright renderer with:
- `page.set_content(html, wait_until="networkidle")`
- `page.pdf(format="A4", print_background=True, margin=...)`
3. Ensure Chromium runtime installed in image (`playwright install chromium` + system deps if needed).
4. Add timeout and circuit-breaker fallback to ReportLab path.

### Task 6: Harden ReportLab fallback renderer

**Files:**
- Modify: `backend/app/domain/utils/markdown_to_pdf.py`
- Modify: `backend/tests/domain/utils/test_markdown_to_pdf.py`

**Steps:**
1. Convert table cells to wrapped `Paragraph` objects and enforce column widths.
2. Add guard to avoid duplicate References if markdown already has a references heading.
3. Make TOC optional by channel defaults (off for Telegram unless forced).
4. Add title sanitization policy for unsupported glyphs.

### Task 7: End-to-end parity verification

**Files:**
- Create: `backend/tests/integration/test_telegram_pdf_visual_contract.py`

**Steps:**
1. Generate PDF from fixture report using Playwright renderer.
2. Extract text with pypdf and verify:
- no missing citation numbers
- one References section
- all source URLs present
3. Verify PDF metadata and file-size constraints (< 50 MB).
4. Add regression fixture matching your real report pattern.

### Task 8: Operational safeguards and observability

**Files:**
- Modify: `backend/app/core/prometheus_metrics.py`
- Modify: `backend/app/domain/services/channels/telegram_delivery_policy.py`

**Steps:**
1. Add metrics by renderer type and failure reason.
2. Add structured logs for citation mismatch diagnostics.
3. Add feature flag for safe rollback to ReportLab.

---

## Acceptance Criteria

1. PDF visual style matches report modal document body (title, headings, paragraph spacing, tables, code blocks, citation badges).
2. Inline citations and references have no mismatch:
- every inline `[N]` has a corresponding reference item
- no duplicate reference headers
- no orphan references without citation
3. No broken table clipping on long rows.
4. No tofu/empty-box glyphs in title/body for common multilingual content.
5. Telegram constraints respected:
- caption <= 1024 chars
- file <= 50 MB
- fallback behavior on renderer failure preserved.

---

## Rollout Strategy

1. **Phase 1 (safe):** Enable Playwright renderer behind feature flag for internal test chats only.
2. **Phase 2 (partial):** 25% of Telegram PDF traffic with automatic fallback.
3. **Phase 3 (full):** Default to Playwright renderer; keep ReportLab fallback enabled.
4. **Phase 4 (cleanup):** Remove obsolete duplicated styling logic after 7-day clean run.

---

## Risks and Mitigations

1. **Chromium startup overhead**
- Mitigation: browser context reuse pool + timeout budget + circuit breaker.

2. **CSS drift between frontend and backend template**
- Mitigation: extract shared report print CSS and consume from both sides.

3. **Citation parser edge cases**
- Mitigation: keep contract tests with mixed citation formats and malformed references.

4. **Dependency/runtime failures in container**
- Mitigation: startup health check for renderer availability and automatic fallback.

---

## Verification Commands (after implementation)

- `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/domain/utils/test_markdown_to_pdf.py tests/domain/services/channels/test_telegram_delivery_policy.py tests/domain/services/pdf/ -q`
- `cd frontend && bun run lint && bun run type-check`

---

## Suggested Execution Order

1. Task 1 (tests-first baseline)
2. Task 2 (abstraction)
3. Task 3 (citation parity normalizer)
4. Task 4 (shared HTML/CSS template)
5. Task 5 (Playwright renderer)
6. Task 6 (ReportLab fallback hardening)
7. Task 7 (integration contract)
8. Task 8 (metrics + rollout)
