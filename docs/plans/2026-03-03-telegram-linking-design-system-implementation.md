# Telegram Linking Design-System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a Telegram account-linking design system in the UI that matches the requested conversational style (intro message + timestamp + `Link Account` redirect + bind command + connected confirmation), with backend behavior aligned to a 30-minute link expiry.

**Architecture:** Keep the existing `channel-links` backend as the source of truth for link code generation and account linking, extend its response contract for UI rendering metadata, and rely on the globally configured Telegram bot token (`TELEGRAM_BOT_TOKEN` in `.env`). In the domain layer, add a `:bind` alias that maps to existing `/link` behavior to match the requested UX text while preserving compatibility.

**Tech Stack:** FastAPI, Pydantic v2, MongoDB + Redis, Vue 3 (`<script setup lang="ts">`), TypeScript strict, existing `AccountSettings` component styles.

---

## ASSUMPTIONS

1. “Design system” means visual/interaction behavior, not a separate design-token package.
2. The requested copy should be branded for Pythinker (not Manus) while preserving message structure.
3. Link expiry should be **30 minutes** (`1800s`) to match UI copy.
4. The redirect button should open the bot URL (`https://t.me/Pythinkbot`) and the UI still shows a command users can send.
5. The command shown in UI should be `:bind <CODE>`, and backend should accept it as an alias for `/link <CODE>`.
6. Per-user Telegram bot token entry is not needed because the app uses one global bot token from `.env`.

If any assumption is wrong, update the plan before implementation.

---

### Task 1: Lock API Contract for 30-Minute Linking Metadata

**Files:**
- Modify: `backend/app/interfaces/schemas/channel_link.py`
- Modify: `backend/app/interfaces/api/channel_link_routes.py`
- Test: `backend/tests/interfaces/api/test_channel_link_routes.py`

**Step 1: Write failing tests for contract changes**

Add tests asserting:
- `expires_in_seconds == 1800` for `POST /api/v1/channel-links/generate`
- response includes `bind_command` with `:bind <CODE>`
- response includes `bot_url` (expected `https://t.me/Pythinkbot`)

```python
assert data["expires_in_seconds"] == 1800
assert data["bind_command"].startswith(":bind ")
assert data["bot_url"] == "https://t.me/Pythinkbot"
```

**Step 2: Run tests to verify RED**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_channel_link_routes.py
```

Expected: failures for new fields / 1800 TTL.

**Step 3: Implement minimal backend schema + route changes**

- Extend `GenerateLinkCodeResponse` with:
  - `bind_command: str`
  - `bot_url: str`
- Set `_CODE_TTL_SECONDS = 1800`
- In generate response:
  - `bind_command = f":bind {code}"`
  - `bot_url = "https://t.me/Pythinkbot"` (or from config if available)

**Step 4: Run tests to verify GREEN**

Run same pytest command; all tests in file pass.

**Step 5: Refactor (if needed)**

Extract helper(s) for bot URL and bind-command generation to keep route readable.

---

### Task 2: Add `:bind` Alias in Domain Command Parsing

**Files:**
- Modify: `backend/app/domain/services/channels/message_router.py`
- Test: `backend/tests/domain/services/channels/test_message_router.py`

**Step 1: Write failing tests for bind alias**

Add tests that inbound content `:bind ABC123`:
- uses the same flow as `/link ABC123`
- returns usage guidance when code missing (`:bind`)

```python
msg = _make_inbound(":bind ABC123")
replies = [r async for r in router.route_inbound(msg)]
assert "Account linked" in replies[0].content
```

**Step 2: Run targeted tests to verify RED**

Run:
```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/channels/test_message_router.py
```

Expected: new bind tests fail.

**Step 3: Implement minimal normalization**

In `route_inbound` command detection:
- detect first token
- if `:bind`, transform content to `/link <payload>` before existing slash-command handling

Also update `HELP_TEXT` to show alias:
- `/link CODE` (or `:bind CODE`)

**Step 4: Run tests to verify GREEN**

Run the same test file; all pass.

**Step 5: Refactor**

Extract `_normalize_channel_command(content: str) -> str` helper for readability.

---

### Task 3: Update Frontend API Types for New Linking Payload

**Files:**
- Modify: `frontend/src/api/channelLinks.ts`

**Step 1: Add/adjust TypeScript interfaces**

Extend `GenerateLinkCodeResponse`:
- `bind_command: string`
- `bot_url: string`

**Step 2: Keep service call contract unchanged**

`generateLinkCode("telegram")` still returns response data object, now with extra fields.

**Step 3: Run type check to verify**

Run:
```bash
cd frontend && bun run type-check
```

Expected: fails until UI updates consume fields correctly, then passes after Task 4.

---

### Task 4: Implement Telegram Design-System UI in Account Settings

**Files:**
- Modify: `frontend/src/components/settings/AccountSettings.vue`

**Step 1: Write minimal component test (if test harness already used)**

If `vitest` component tests exist for settings, add a test verifying:
- intro text renders
- `Link Account` button appears when link code exists
- bind command line renders

If no practical harness exists, skip test file creation and rely on lint/type-check + manual verification (documented in final notes).

**Step 2: Replace current “code steps” block with requested conversation-style card**

When `linkCode` state is active, render:
- Message bubble:
  - “To continue, you need to link your Telegram account with Pythinker.”
  - “Click the button below to get started. This link will expire in 30 minutes.”
  - Timestamp (local time)
- CTA button:
  - Label: `Link Account`
  - `href` from `result.bot_url`
  - opens new tab (`target="_blank"`, `rel="noopener noreferrer"`)
- Command bubble:
  - `:bind <CODE>` from `result.bind_command`
  - copy button
- Optional connected-state helper bubble when `telegramLinked`:
  - “I’m now connected and ready to help you!...”

**Step 3: Remove per-user token gating**

- Remove token-setup entry UI/state from `AccountSettings`.
- Link flow becomes: click `Link Account` flow -> generate payload -> show design-system card.

**Step 4: Add CSS for message-style visual system**

Add scoped styles:
- bot-message bubble style
- timestamp typography
- CTA button style
- command-chip / copy interaction style
- success message style

No global theme token changes unless necessary.

**Step 5: Run frontend validation**

Run:
```bash
cd frontend && bun run lint && bun run type-check
```

Expected: both pass.

---

### Task 5: End-to-End Verification and Regression Checks

**Files:**
- No new files unless fixes are needed.

**Step 1: Backend targeted checks**

Run:
```bash
conda activate pythinker && cd backend && ruff check app/interfaces/api/channel_link_routes.py app/interfaces/schemas/channel_link.py app/domain/services/channels/message_router.py tests/interfaces/api/test_channel_link_routes.py tests/domain/services/channels/test_message_router.py
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_channel_link_routes.py tests/domain/services/channels/test_message_router.py
```

**Step 2: Frontend checks**

Run:
```bash
cd frontend && bun run lint && bun run type-check
```

**Step 3: Manual acceptance checklist**

1. Open Settings → Account → Linked Channels.
2. Unlinked state shows the new conversation-style card when linking starts.
3. `Link Account` opens Telegram bot.
4. `:bind <CODE>` copy works.
5. Sending `:bind <CODE>` in Telegram links account.
6. Linked state shows connected confirmation copy.

**Step 4: Verify no unrelated regressions in existing channel-link flows**

- Existing `/link CODE` still works.
- Unlink flow still works.

---

### Task 6: Final Cleanup + Changelog Summary

**Files:**
- Modify (if needed): `docs/plans/2026-03-03-telegram-linking-design-system-implementation.md` (status notes)

**Step 1: Ensure only intended files changed**

Run:
```bash
git status --short
```

**Step 2: Prepare factual completion report**

Include:
- Completed vs in-progress items
- exact test commands run and results
- any deferred items

---

## ROLLOUT NOTES

- This repo is development-only; no migration is required for TTL change.
- Existing saved link codes (15m) will naturally expire.
- Existing per-user token docs (if present from prior experiments) can be ignored or cleaned up separately.

## OPEN QUESTIONS TO RESOLVE DURING IMPLEMENTATION

1. Should copy say “with Manus” verbatim, or “with Pythinker”?
2. Should bot URL be hardcoded to `@Pythinkbot` or moved to env (`VITE_TELEGRAM_BOT_URL`)?
3. Should linked success message be persistent or dismissible?
