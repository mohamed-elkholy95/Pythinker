# Telegram Context Continuity + PDF Delivery Design

## Goal

Deliver a robust Telegram channel experience with:

1. **Conversation continuity** so Telegram chats retain context across turns.
2. **Automatic PDF delivery** for research reports or very long responses, sent back into the same Telegram chat.

This design is backend-first and integrates with the existing gateway pipeline:

`TelegramChannel -> NanobotGateway -> MessageRouter -> AgentService -> MessageRouter -> NanobotGateway -> TelegramChannel`

## ASSUMPTIONS I'M MAKING

1. Telegram users expect conversational memory by default unless they explicitly reset with `/new`.
2. Losing context currently happens because completed sessions are treated as terminal and replaced on next user message.
3. PDF delivery should be channel-specific (Telegram only) and not alter web chat behavior.
4. PDF generation must remain self-hosted/open-source with no paid external dependency.
5. This repository is development-only, so schema evolution can be forward-only and aggressively iterative.

---

## Current Gaps

### 1) Context reset on completed sessions

In `backend/app/domain/services/channels/message_router.py`, `_get_or_create_session()` currently considers `completed` terminal and creates a new session. That breaks continuity in Telegram because most turns complete quickly.

### 2) No structured file delivery path from channel events

`MessageRouter._event_to_outbound()` currently maps `message/report/error` to text only. It does not map report/long-form output to file attachments for channel delivery.

### 3) Telegram adapter can already send documents, but domain layer does not feed it

`backend/nanobot/channels/telegram.py` already supports `send_document` via outbound `media`, but Pythinker outbound events rarely include media for text/report events.

---

## Telegram API Hard Limits (Context7-Validated)

These constraints are authoritative and must be enforced in both the delivery policy and adapter layers.

| Constraint | Limit | Source |
|---|---|---|
| `sendMessage` text | **4096 chars** after entity parsing | Telegram Bot API |
| `sendDocument` file size | **50 MB** via multipart upload | Telegram Bot API |
| `sendDocument` caption | **1024 chars** after entity parsing | Telegram Bot API |
| `sendDocument` via URL | Only `.PDF` and `.ZIP` supported | Telegram Bot API |
| Message splitting | Existing `_split_message()` in `telegram.py:82-99` chunks at **4000 chars** | Codebase |

**Implications**:
- PDF caption (summary + boilerplate) must fit within 1024 chars — requires a truncation strategy.
- The existing `_split_message()` chunker is the fallback path — delivery policy delegates to it, does not reimplement.
- `sendDocument` via URL only supports PDF/ZIP, so local file upload (multipart) is the correct approach.

---

## Proposed Architecture

## A) Telegram Context Continuity Policy

Introduce a channel-aware reuse policy in `MessageRouter`:

- For **Telegram**:
  - Reuse existing session when status is `running`, `pending`, `initializing`, `waiting`, **or `completed`**.
  - Rotate session only when:
    - user sends `/new`
    - session missing/deleted
    - session status is `failed` or `cancelled`
    - optional inactivity timeout exceeded (configurable)
- For other channels:
  - Keep current behavior initially.

### Required changes

1. Add a policy helper (e.g. `_should_reuse_session(message, session)`).
2. Add Telegram continuity config flags in `ChannelSettingsMixin`:
   - `telegram_reuse_completed_sessions: bool = True`
   - `telegram_session_idle_timeout_hours: int = 168` (7 days default)
3. Track per-chat activity in `channel_sessions`:
   - `last_inbound_at`
   - `last_outbound_at`
4. Add context-window controls (P1):
   - `telegram_max_context_turns: int = 50`
   - `telegram_context_summarization_enabled: bool = True`
   - `telegram_context_summarization_threshold_turns: int = 50`
5. Persist rolling summary metadata for long chats (P1):
   - `context_turn_count`
   - `context_summary`
   - `context_summary_updated_at`

6. Add `/pdf` slash command to `SLASH_COMMANDS` in `message_router.py`:
   - Forces PDF delivery for the **last response** in the current session.
   - Useful when a user wants a PDF of content below the auto-threshold.
   - Pattern: `/pdf` → look up last `ReportEvent` or `MessageEvent` → run delivery policy with `force_pdf=True`.

This preserves chat context naturally while allowing deterministic resets.

**Activity tracking implementation note**: `last_inbound_at` / `last_outbound_at` updates should be performed via the repository layer on every `route_inbound()` / `send_to_channel()` call, not via direct MongoDB writes in the router. This keeps domain layer clean.

---

## B) Telegram PDF Delivery Policy

Add a dedicated domain service:

`backend/app/domain/services/channels/telegram_delivery_policy.py`

Responsibilities:

1. Decide delivery mode:
   - `text`
   - `pdf_only`
   - `text_plus_pdf`
2. Build PDF from report/long content.
3. Return `OutboundMessage` with `MediaAttachment` when PDF is selected.
4. Fallback to chunked text on any PDF failure.
5. Normalize and sanitize markdown/text before PDF rendering.
6. Add PDF metadata (title/author/subject/creator/timestamp) for searchability.

### Trigger rules (default)

Generate PDF if **any**:

1. `event.type == "report"` and content length >= `telegram_pdf_report_min_chars` (default 2000).
2. `event.type == "message"` and content length >= `telegram_pdf_message_min_chars` (default 3500).
3. Content appears report-like (headings + references/citations).
4. User explicitly requests via `/pdf` slash command (`force_pdf=True`).

For **borderline content** (within 20% of threshold):
- Send text normally but include a Telegram `InlineKeyboardMarkup` button: **"Get as PDF"**.
- Callback triggers PDF generation on-demand without surprising users with unwanted attachments.
- The nanobot Telegram adapter already supports `reply_markup` through outbound message metadata.

For very large payloads:

- If content length >= `telegram_pdf_async_threshold_chars` (default 10000), use async delivery:
  1. send immediate acknowledgement message ("Generating PDF report...")
  2. generate PDF in background
  3. send PDF with `reply_to` linked to the acknowledgement message

### Output shape

- `OutboundMessage.content`: short summary + "Full report attached as PDF." — **must fit within 1024 chars** (Telegram caption limit).
  - Budget: ~900 chars for summary text, ~124 chars for boilerplate/formatting.
  - Truncation strategy: truncate at last complete sentence boundary within budget.
- `OutboundMessage.media`: one `MediaAttachment` with local file path, filename, mime type.
- `OutboundMessage.metadata`: include `delivery_mode`, `report_title`, generation diagnostics, and `parse_mode: "HTML"`.
  - Use `parse_mode=HTML` for captions — the existing `_markdown_to_telegram_html()` converter in `telegram.py:19-79` already handles this conversion.
  - Do NOT use `MarkdownV2` — it requires escaping 19+ special characters and is fragile for generated content.

### Leveraging ReportEvent structured fields

The existing `ReportEvent` model carries structured data that the PDF generator should use:

```python
# From backend/app/domain/models/event.py
class ReportEvent:
    title: str                              # → PDF title page / header
    content: str                            # → PDF body (Markdown)
    attachments: list[FileInfo] | None      # → Embedded file links
    sources: list[SourceCitation] | None    # → References/bibliography section
```

The delivery policy must extract and forward these fields to the PDF engine, not just raw `content`.

### PDF engine

Use **ReportLab** (open-source, self-hosted) as the default generator:

- deterministic
- no headless browser dependency for simple text PDFs
- stable in server environments

Fallback chain:

1. ReportLab PDF
2. Plain text chunked Telegram message (existing `_split_message()` at `telegram.py:82-99`)

### Markdown → ReportLab conversion layer

Create a standalone utility module:

`backend/app/domain/utils/markdown_to_pdf.py`

Provides `markdown_to_flowables(content: str) -> list[Flowable]` that handles:

| Markdown element | ReportLab Flowable |
|---|---|
| `# Heading` | `Paragraph` with heading ParagraphStyle |
| Body text | `Paragraph` with normal style |
| `**bold**` / `*italic*` | Inline `<b>` / `<i>` XML tags in Paragraph |
| Code blocks | `Preformatted` or `XPreformatted` with monospace font |
| Bullet/numbered lists | `ListFlowable` / `ListItem` |
| Tables | ReportLab `Table` with `TableStyle` |
| Links | `<a href="...">` tags in Paragraph XML |
| `---` (horizontal rule) | `HRFlowable` |

This is ~100-150 lines and must be unit-testable as a pure function (no I/O).

### Table of Contents for long reports

For reports with >= `telegram_pdf_toc_min_sections` (default 3) headings, auto-generate a TOC using ReportLab's `TableOfContents` + `multiBuild()` pattern:

- Subclass `BaseDocTemplate` with `afterFlowable()` hook to register heading entries.
- TOC placed after title page, before body content.
- Adds ~30 lines to the PDF engine. Context7-validated pattern from ReportLab docs.

### PDF metadata

Set `SimpleDocTemplate` metadata for searchability in file managers:

- `title`: from `ReportEvent.title` or auto-generated from first heading
- `author`: "Pythinker AI Agent"
- `subject`: session topic or first 100 chars of content
- `creator`: "Pythinker / ReportLab"

### PDF file_id caching (P1)

After a document is sent, the Telegram API response includes a `file_id`. Cache `(content_hash → file_id)` in Redis with 24h TTL. If the same report is requested again (e.g., via `/pdf` or by another user), reuse the `file_id` for instant delivery without re-upload.

### Language/font strategy (P1)

Add script-aware font fallback for multilingual reports:

- latin: `DejaVuSans` (default — bundled with Linux, full Unicode Latin/Cyrillic/Greek coverage)
  - **Critical**: ReportLab's built-in fonts (Times-Roman, Helvetica, Courier) only support Latin-1.
  - Using `DejaVuSans` via `TTFont` + `registerFont()` is a 3-line fix that prevents silent character loss.
  - Config: `telegram_pdf_unicode_font: str = "DejaVuSans"`
- cjk: `NotoSansCJK` (if available, else fallback to DejaVuSans + warning)
- arabic: `NotoSansArabic` (if available, else fallback + warning)

If a required font is unavailable, generator must still succeed and emit a structured warning metric/log.

---

## C) Telegram Adapter Enhancements

`backend/nanobot/channels/telegram.py`

Enhancements:

1. Support document captions via outbound metadata (`caption`).
2. Respect Telegram-safe limits for caption and message length.
3. Add post-send cleanup hook for temporary generated PDFs.
4. Add Telegram rate-limit and transient error handling:
   - handle `RetryAfter` by sleeping for provided delay
   - bounded retry for transient network/timeouts
   - final fallback: chunked text response if document send repeatedly fails

No change to the existing command handlers is required for this feature.

---

## Data + Config Changes

## Config (`ChannelSettingsMixin` in `config_channels.py`)

Add:

**Context continuity:**
- `telegram_reuse_completed_sessions: bool = True`
- `telegram_session_idle_timeout_hours: int = 168`
- `telegram_max_context_turns: int = 50`
- `telegram_context_summarization_enabled: bool = True`
- `telegram_context_summarization_threshold_turns: int = 50`

**PDF delivery:**
- `telegram_pdf_delivery_enabled: bool = True`
- `telegram_pdf_message_min_chars: int = 3500` — threshold for `message` events
- `telegram_pdf_report_min_chars: int = 2000` — threshold for `report` events
- `telegram_pdf_caption_max_chars: int = 900` — caption budget (Telegram limit: 1024)
- `telegram_pdf_async_threshold_chars: int = 10000`
- `telegram_pdf_cleanup_seconds: int = 600`
- `telegram_pdf_include_toc: bool = True` — auto TOC for multi-section reports
- `telegram_pdf_toc_min_sections: int = 3` — minimum headings to trigger TOC
- `telegram_pdf_unicode_font: str = "DejaVuSans"` — default Unicode font
- `telegram_pdf_rate_limit_per_minute: int = 5` — per-user PDF generation rate limit
- `telegram_pdf_max_generation_seconds: int = 30`
- `telegram_pdf_max_memory_mb: int = 100`

**Adapter resilience:**
- `telegram_rate_limit_cooldown_seconds: int = 3`
- `telegram_max_messages_per_batch: int = 5`

## Mongo (`channel_sessions`)

Add non-breaking fields:

- `last_inbound_at: datetime`
- `last_outbound_at: datetime`
- `context_turn_count: int`
- `context_summary: str | None`
- `context_summary_updated_at: datetime | None`

Index:

- `(user_id, channel, chat_id)` already exists; no migration needed.
- Optional additional index on `updated_at` for cleanup jobs.

---

## Reliability and Safety

1. **Resource safety**
   - Cap PDF size before send (Telegram `sendDocument` limit: **50 MB** multipart).
   - Enforce generation runtime/memory ceilings.
   - Cleanup temp PDFs after successful send or on timeout.
   - Per-user PDF rate limit: `telegram_pdf_rate_limit_per_minute` (default 5) using existing Redis rate governor pattern from search API resilience work (`backend/app/infrastructure/external/search/rate_governor.py`).
2. **Delivery resilience**
   - Handle Telegram API transient failures with bounded retries and backoff.
   - Respect `RetryAfter` when the API requests cooldown.
   - Fallback to chunked text if PDF send fails after retries.
3. **Content safety**
   - Sanitize control characters and malformed markdown segments before PDF render.
   - Validate temp file paths to prevent traversal/unsafe writes.
4. **Graceful degradation**
   - Any PDF generation/send failure falls back to existing text delivery.
5. **Observability**
   - Add metrics:
     - `telegram_session_reused_total`
     - `telegram_session_rotated_total{reason}`
     - `telegram_pdf_generated_total`
     - `telegram_pdf_generation_failed_total{reason}`
     - `telegram_pdf_sent_total`
   - Add structured logs:
      - `telegram.session.reuse`
      - `telegram.session.rotate`
      - `telegram.pdf.generate.start`
      - `telegram.pdf.generate.success`
      - `telegram.pdf.generate.fallback`
   - Add tracing spans (P1):
      - `telegram.delivery.policy`
      - `telegram.pdf_generation`
      - `telegram.telegram_send`

---

## Testing Plan

## Unit tests

1. `test_message_router.py`
   - completed Telegram session is reused
   - `/new` still resets context
   - `/pdf` triggers PDF delivery for last response
   - failed/cancelled still rotate
   - non-Telegram channels keep original terminal behavior
2. `test_telegram_delivery_policy.py` (new)
   - report triggers PDF at `telegram_pdf_report_min_chars` threshold
   - message triggers PDF at `telegram_pdf_message_min_chars` threshold
   - short text stays inline
   - borderline content returns inline keyboard button
   - generation failure falls back to text
   - caption output fits within `telegram_pdf_caption_max_chars`
   - sanitization preserves generator safety for malformed inputs
   - async threshold path sends ack + later document
   - rate limit exceeded returns text fallback
3. `test_markdown_to_pdf.py` (new)
   - headings → Paragraph with heading styles
   - code blocks → Preformatted flowable
   - tables → ReportLab Table
   - bullet/numbered lists → ListFlowable
   - links preserved as `<a>` tags
   - Unicode text renders with DejaVuSans (no silent char loss)
   - TOC generated when heading count >= threshold
   - ReportEvent.sources → bibliography section
   - PDF metadata (title, author) set correctly

## Integration tests

1. `test_nanobot_gateway.py`
   - outbound `MediaAttachment` converts to nanobot media path
2. `test_telegram_channel_commands.py`
   - document send path includes caption and uses `send_document`
   - transient Telegram send failures trigger retry/backoff behavior
   - `RetryAfter` is respected

## Regression checks

- Existing `/link`, `/status`, `/stop`, `/new` behavior remains unchanged.
- Existing non-Telegram channel behavior remains unchanged.
- Existing `_split_message()` chunking logic is not duplicated or broken.
- Web chat delivery path is completely unaffected (PDF is Telegram-only).

---

## Implementation Phases

### Phase 1 (P0): Context continuity

Status: `Not Started`

- Change MessageRouter reuse policy for Telegram completed sessions.
- Add `_should_reuse_session(message, session)` policy helper.
- Add `last_inbound_at` / `last_outbound_at` tracking fields to `channel_sessions` (even though inactivity rotation is Phase 5 — adding the fields now costs nothing and prevents a later schema change).
- Add `/pdf` to `SLASH_COMMANDS` dict (handler can be a no-op stub until Phase 2b).
- Add config flags to `ChannelSettingsMixin`.
- Add coverage in `test_message_router.py`.

### Phase 2a (P0): Markdown → PDF engine

Status: `Not Started`

- Create `backend/app/domain/utils/markdown_to_pdf.py` — pure function `markdown_to_flowables()`.
- Register `DejaVuSans` as default Unicode font.
- Implement TOC generation for multi-section reports.
- Set PDF metadata (title, author, subject, creator).
- Build bibliography section from `ReportEvent.sources`.
- Add comprehensive unit tests in `test_markdown_to_pdf.py`.
- **This phase is pure-function, no I/O, easy to develop and test in isolation.**

### Phase 2b (P0): Delivery policy + wiring

Status: `Not Started`

- Create `telegram_delivery_policy.py` — decides delivery mode, builds `OutboundMessage` with `MediaAttachment`.
- Wire into `MessageRouter._event_to_outbound()` for report/long-message events.
- Implement caption truncation at sentence boundary within `telegram_pdf_caption_max_chars`.
- Implement `/pdf` slash command handler (calls delivery policy with `force_pdf=True`).
- Add per-user PDF rate limiting via existing Redis rate governor.
- Ensure `parse_mode=HTML` is set in outbound metadata for captions.
- Add unit tests in `test_telegram_delivery_policy.py`.

### Phase 3 (P1): Adapter + cleanup + metrics

Status: `Not Started`

- Add caption support in Telegram adapter (read `parse_mode` + `caption` from outbound metadata).
- Add post-send cleanup hook for temporary PDFs.
- Add metric instrumentation (counters + structured logs).
- Add inline keyboard "Get as PDF" button for borderline-length content.
- Delegate fallback to existing `_split_message()` — no reimplementation.

### Phase 4 (P1): Caching + hardening

Status: `Not Started`

- Add `file_id` caching in Redis (`content_hash → file_id`, 24h TTL) for instant re-delivery.
- Add Telegram `RetryAfter` handling and bounded retry in adapter.
- Add robustness tests (malformed input, large payload, retry/fallback, Unicode edge cases).

### Phase 5 (P2): Advanced features

Status: `Not Started`

- Add context summarization when turn threshold is exceeded.
- Add async PDF generation mode for large content (>10k chars).
- Add multilingual font fallback (CJK, Arabic) and tracing spans.
- Add inactivity-based session rotation using `last_inbound_at` timestamps.

---

## External Constraints (for implementation)

- `sendMessage` text: **4096 chars** (after entity parsing). Existing `_split_message()` chunks at 4000.
- `sendDocument` file: **50 MB** multipart upload. Cap PDF before send.
- `sendDocument` caption: **1024 chars** (after entity parsing). Budget ~900 for summary.
- `parse_mode`: Use **HTML** for captions (existing converter handles this). Avoid MarkdownV2.
- ReportLab default fonts only support Latin-1 — **must register a Unicode TTF** (`DejaVuSans`).
- Keep generated files local/ephemeral unless explicit persistence is needed.
- ReportLab `multiBuild()` required for TOC generation (two-pass rendering).

## New Files Created by This Plan

| File | Phase | Purpose |
|---|---|---|
| `domain/utils/markdown_to_pdf.py` | 2a | Pure Markdown → ReportLab flowables converter |
| `domain/services/channels/telegram_delivery_policy.py` | 2b | Delivery mode decision + PDF orchestration |
| `tests/domain/utils/test_markdown_to_pdf.py` | 2a | Unit tests for converter |
| `tests/domain/services/channels/test_telegram_delivery_policy.py` | 2b | Unit tests for policy |

## Files Modified by This Plan

| File | Phase | Change |
|---|---|---|
| `domain/services/channels/message_router.py` | 1, 2b | Reuse policy, `/pdf` command, delivery policy wiring |
| `core/config_channels.py` | 1 | New config flags (~15 fields) |
| `nanobot/channels/telegram.py` | 3 | Caption support, cleanup hook, retry handling |
| `infrastructure/external/channels/nanobot_gateway.py` | 3 | Ensure media paths + metadata preserved |
