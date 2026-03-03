# Unified Nanobot + Agents Tab + Telegram Workflow Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align `backend/nanobot` channel behavior with the `/chat/agents` experience so Telegram linking, command handling, and Telegram-session search work consistently end-to-end.

**Architecture:** Keep nanobot as channel runtime, keep `MessageRouter` as the domain command bridge, and make the frontend consume one unified Telegram workspace model (link state + channel health + filtered sessions/search). Fix command forwarding first, then unify UI and search behavior.

**Tech Stack:** FastAPI, python-telegram-bot v22.x, MongoDB, Redis, Vue 3 + TypeScript, Vitest, Pytest.

---

## ASSUMPTIONS I'M MAKING

1. `@nanobot/` means the vendored channel runtime under `backend/nanobot`.
2. "Agents tab" means `frontend/src/pages/AgentsPage.vue` at route `/chat/agents`.
3. "Telegram search" means searching/filtering Telegram-origin sessions in the UI (and optionally via backend query params).
4. The desired behavior is one-click link flow that works with Telegram deep links, not copy/paste fallback as the primary path.
5. Development workflow should support Telegram linking without requiring hidden manual steps.

If any assumption is wrong, update before implementation.

---

## Current Assessment (Status)

- `Completed`: Repo workflow mapping and code-path analysis
- `Completed`: Telegram deep-link behavior validation against docs
- `Completed`: Detection of current workflow obstructions
- `Completed`: Frontend composable extraction and link-flow deduplication (Phase 3 partial)
- `Completed`: Backend source-field plumbing and uppercase code normalization (Phase 4 partial)
- `Not Started`: Adapter command forwarding fixes (Phase 1 — critical path blocker)
- `Not Started`: Dev gateway availability (Phase 2)
- `Not Started`: Shared link card component and navigation fix (Phase 3 remainder)
- `Not Started`: Search/filter UI controls (Phase 4 remainder)
- `Not Started`: Observability (Phase 5)
- `Not Started`: Test closure (Phase 6)

---

## Completed Prerequisites (2026-03-03)

The following foundational work was completed before this plan's implementation phases begin. These changes are uncommitted and should be committed as atomic commits before starting Phase 1.

### Backend fixes already applied

| Fix | Files | Detail |
|-----|-------|--------|
| Uppercase code normalization | `channel_link_routes.py`, `message_router.py`, `test_channel_link_routes.py`, `test_channel_integration.py` | `_CODE_ALPHABET` changed to `string.ascii_uppercase + string.digits`; router does single `.upper()` lookup instead of multi-key loop |
| Channel session cleanup on unlink | `user_channel_repository.py` | `unlink_channel()` now runs `delete_many` on `channel_sessions` to prevent orphaned session mappings |
| Session source field | `session.py` (schema), `session_routes.py` | `ListSessionItem` exposes `source: str = "web"` in both GET and SSE session-list endpoints |
| Frontend source type | `response.ts` | `ListSessionItem` interface includes `source: string` |

### Frontend fixes already applied

| Fix | Files | Detail |
|-----|-------|--------|
| `useTelegramLink` composable | `composables/useTelegramLink.ts` (NEW) | Shared reactive lifecycle: code generation, countdown, clipboard, deep-link (`?start=` preferred), 5s poll, cleanup |
| AgentsPage composable integration | `pages/AgentsPage.vue` | Destructured composable; sessions filtered by `source === 'telegram'`; auto-redirect on linked state removed |
| AgentSettings composable integration | `components/settings/AgentSettings.vue` | All telegram state/methods replaced with composable; `onUnmounted` cleanup delegated |
| AccountSettings composable integration | `components/settings/AccountSettings.vue` | All telegram state/methods replaced with composable; unlink flow and loading skeleton kept local |

**Net change:** 141 insertions, 591 deletions across 11 modified files, plus 1 new implementation file (`useTelegramLink.ts`) and this plan document.

---

## Current Workflow Map

1. User opens `/chat/agents` and clicks `Get started on Telegram`.
2. Frontend calls `POST /api/v1/channel-links/generate`.
3. Backend returns `code`, `bind_command`, `bot_url`, `deep_link_url`.
4. Frontend opens Telegram deep link via `useTelegramLink.openDeepLink()`.
5. Telegram sends `/start bind_<CODE>` when the user presses START.
6. **BROKEN:** Message is intercepted by `_on_start()` in `telegram.py` which sends a local greeting and never forwards the bind payload.
7. ~~Router normalizes to `/link <CODE>`, redeems Redis code, links account.~~ (never reached)

---

## Obstruction Register

### Critical — Blocks core flow

1. **Deep-link payload is swallowed before router normalization**
   - Status: **OPEN — P0 blocker**
   - Evidence:
     - `backend/nanobot/channels/telegram.py:292-302`: `_on_start()` sends a local greeting reply ("Hi {user.first_name}! I'm nanobot...") and returns. The handler does NOT check `context.args` for bind payload.
     - `backend/app/domain/services/channels/message_router.py:366-369`: alias normalization `if command == "/start" and argument.lower().startswith("bind_")` exists but is dead code — never receives `/start` messages from the adapter.
   - Impact: one-click deep-link linking is completely non-functional; users stay in "Activation pending" forever.
   - Fix: Phase 1.

2. **Command handling mismatch in Telegram adapter**
   - Status: **OPEN — P0 blocker**
   - Evidence:
     - Only 3 `CommandHandler` registrations in `telegram.py`: `start`, `new`, `help`.
     - `filters.TEXT & ~filters.COMMAND` (line 156-162) explicitly excludes all `/` prefixed messages from the text handler.
     - `/stop`, `/status`, `/link` are recognized by `MessageRouter.SLASH_COMMANDS` but have no `CommandHandler` in the adapter.
     - Result: these commands are silently dropped — user gets no response in Telegram.
   - Impact: `/stop`, `/status`, `/link` cannot be used from Telegram.
   - Fix: Phase 1.

3. **Dev runtime gap: gateway not started in default dev workflow**
   - Status: **OPEN**
   - Evidence:
     - `dev.sh` uses `docker-compose-development.yml` which has no `gateway` service.
     - `gateway` exists only in `docker-compose.yml` under `profiles: ["gateway"]`.
   - Impact: Telegram UI flow appears healthy in dev while channel pipeline is offline.
   - Fix: Phase 2.

### High — UX consistency

4. **~~UI surface fragmentation across three pages~~**
   - Status: **RESOLVED** (composable extraction completed 2026-03-03)
   - `useTelegramLink` composable handles all shared state; timer/polling/countdown logic is no longer duplicated.
   - Remaining: template markup for the link card is still copied across 3 components (see Phase 3 remainder).

5. **Agents tab lacks Telegram-specific search/filter controls**
   - Status: **PARTIALLY RESOLVED**
   - Done: sessions filtered by `source === 'telegram'` client-side.
   - Remaining: no query input, no status filter dropdown, no backend query params.
   - Fix: Phase 4.

6. **Navigation misalignment from settings**
   - Status: **OPEN**
   - Evidence: `AgentSettings.vue:478-480` still routes "Open Task List" to `/chat/history` instead of `/chat/agents`.
   - Fix: Phase 3 remainder.

### Medium — Quality

7. **Test gaps around Telegram adapter behavior**
   - Status: **OPEN**
   - No test file at `tests/infrastructure/external/channels/test_telegram_channel_commands.py`.
   - Fix: Phase 6.

8. **Existing frontend expectation drift**
   - Status: **REGRESSION INTRODUCED** (auto-redirect removed but test not updated)
   - `frontend/src/pages/__tests__/AgentsPage.spec.ts` line 72-89 expects `push('/chat/session-1')` on linked state. This now fails because AgentsPage shows the linked workspace instead of redirecting.
   - Fix: Phase 6 (P1 — should be fixed before merging current changes).

9. **Link observability is minimal**
   - Status: **OPEN**
   - Fix: Phase 5.

---

## Vendoring Policy Decision

Phase 1 requires modifying `backend/nanobot/channels/telegram.py`, which is a vendored package. Two options:

### Option A: Targeted in-place patches (Recommended)
- Add `# PYTHINKER-PATCH: <description>` comments around each modification.
- Minimal diff, easy to review and port if nanobot is updated.
- Already precedented: nanobot is excluded from ruff/coverage in `pyproject.toml` and documented as "zero modifications" — but the adapter behavior makes it impossible to integrate without changes.

### Option B: Subclass in infrastructure layer
- Create `PythinkerTelegramChannel(TelegramChannel)` in `backend/app/infrastructure/external/channels/`.
- Override `_on_start()`, add new command handlers.
- Cleaner DDD boundary but requires wiring the subclass into gateway startup.

**Recommendation:** Option A. The modifications are adapter-level glue (command routing), not business logic. Mark each patch clearly so future nanobot updates can be reconciled.

---

## External Validation Notes

1. Telegram deep links pass a `/start` payload and enforce restricted payload characters/length.
2. python-telegram-bot `CommandHandler` exposes command arguments via `context.args`.
3. `filters.TEXT & ~filters.COMMAND` intentionally excludes slash commands from that message handler.
4. `context.args` for `/start bind_ABC` will be `["bind_ABC"]` — a list of strings split by whitespace after the command.

Primary references:
- https://core.telegram.org/bots/api
- https://docs.python-telegram-bot.org/en/v22.3/telegram.ext.commandhandler.html
- https://docs.python-telegram-bot.org/en/stable/telegram.ext.filters.html
- https://docs.python-telegram-bot.org/en/v22.2/telegram.helpers.html

---

## Design Alternatives

### Option A: Minimal Patch-Only
- Fix deep-link forwarding and command handlers only.
- Pros: quickest stabilization.
- Cons: keeps weak search model (partially mitigated by completed composable work).

### Option B: Unified Telegram Workspace (Recommended)
- Fix backend command correctness.
- ~~Add one frontend Telegram linking module reused in all surfaces.~~ (Done: composable)
- Add shared link card component to deduplicate template markup.
- Add Telegram session search/filter model and optional backend query support.
- Pros: resolves current breakpoints and future drift.
- Cons: moderate cross-layer work (reduced by completed prerequisites).

### Option C: Merge gateway into backend app process
- Start gateway from backend lifespan.
- Pros: simpler ops topology.
- Cons: tighter coupling, harder failure isolation, larger blast radius.

**Recommendation:** Option B.

---

## Unified Target Workflow

1. User clicks `Link Account` from Agents tab or Settings.
2. Backend generates one-time uppercase code and `?start=bind_<CODE>` deep link.
3. Telegram `/start bind_<CODE>` reaches adapter, payload is detected and forwarded to message bus.
4. Router normalizes to `/link <CODE>`, redeems uppercase Redis key, links account.
5. UI receives linked status through 5-second polling.
6. User searches Telegram sessions directly in Agents tab (query + status).
7. Opening any Telegram session routes to `/chat/:sessionId`.

---

## Phase Plan

### Phase 1: Command and Deep-Link Correctness — P0

> **This is the critical-path blocker.** Without this fix, the entire Telegram linking flow silently fails even though the frontend generates correct `?start=bind_CODE` deep links.

**Status:** Not Started

**Files**
- Modify: `backend/nanobot/channels/telegram.py`
- Modify: `backend/tests/integration/test_channel_integration.py`
- Add: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Changes**

1. **Payload-aware `/start` handler** — modify `_on_start()`:
   ```python
   # PYTHINKER-PATCH: forward bind payload to message bus
   async def _on_start(self, update, context):
       if context.args and context.args[0].startswith("bind_"):
           # Reconstruct as "/start bind_<CODE>" and route through message bus
           payload = " ".join(context.args)
           text = f"/start {payload}"
           await self._handle_message(update, context, override_text=text)
           return
       # Original greeting for plain /start
       await update.message.reply_text(f"Hi {update.effective_user.first_name}! ...")
   ```
   Note: `_handle_message` may need an `override_text` parameter if it reads `update.message.text` directly. Check and adapt.

2. **Register command forwarding handlers** for `/stop`, `/status`, `/link`:
   ```python
   # PYTHINKER-PATCH: forward router-supported commands
   app.add_handler(CommandHandler("stop", self._forward_command))
   app.add_handler(CommandHandler("status", self._forward_command))
   app.add_handler(CommandHandler("link", self._forward_command))
   ```

3. **Fallback unknown command handler** (lowest priority group):
   ```python
   # PYTHINKER-PATCH: hint for unrecognized commands
   app.add_handler(MessageHandler(filters.COMMAND, self._unknown_command), group=1)
   ```
   Where `_unknown_command` replies: "Unknown command. Use /help to see available commands."

**Acceptance**
- `/start bind_<CODE>` links successfully without manual copy/paste.
- `/stop`, `/status`, `/link` work in Telegram as documented by router help.
- Plain `/start` (no args) still shows the greeting.
- Unknown commands (e.g., `/foo`) get a help hint.

---

### Phase 2: Dev Gateway Availability

**Status:** Not Started

**Files**
- Modify: `dev.sh`
- Optionally modify: `docker-compose-development.yml`
- Modify: `QUICK_START_2026.md` or add inline `dev.sh` help text

**Changes**
- Add `--gateway` flag to `dev.sh watch` that passes `--profile gateway` to docker compose.
- Print a notice when starting without `--gateway`: "Telegram channel pipeline not started. Use --gateway to enable."
- Keep gateway opt-in to avoid resource overhead for developers not working on Telegram features.

**Acceptance**
- `./dev.sh watch --gateway` starts full stack including channel pipeline.
- Fresh local dev setup can complete full link flow end-to-end.
- Missing gateway is clearly communicated, not silently absent.

---

### Phase 3: Frontend Flow Unification — Remainder

**Status:** ~70% Complete

**Already done:**
- `useTelegramLink` composable extracted and wired to all 3 components.
- Deep link uses `?start=` instead of `?text=`.
- No duplicated timer/polling/countdown logic outside composable.
- Auto-redirect removed from AgentsPage.

**Remaining work:**

**Files**
- Add: `frontend/src/components/telegram/TelegramLinkCard.vue`
- Modify: `frontend/src/pages/AgentsPage.vue` (use shared card)
- Modify: `frontend/src/components/settings/AccountSettings.vue` (use shared card)
- Modify: `frontend/src/components/settings/AgentSettings.vue` (use shared card + fix route)

**Changes**

1. **Shared `TelegramLinkCard.vue`** — extract the bind-command display panel (code field, countdown, copy button, "Open Telegram" action, feedback/error messages) into one reusable component. Each consumer passes composable state via props or `v-bind`.

2. **Fix "Open Task List" route** — change `AgentSettings.vue:478-480`:
   ```typescript
   // Before
   void router.push('/chat/history')
   // After
   void router.push('/chat/agents')
   ```

3. **Align labels** — audit all three surfaces for consistent wording:
   - Button: "Link Account" (not "Get started on Telegram")
   - Status: "Connected" / "Activation pending" / "Not connected"
   - Action: "Open Telegram" (not "Continue on Telegram")

**Acceptance**
- Same link card UI across all three surfaces (single source of template truth).
- "Open Task List" navigates to `/chat/agents`.
- Consistent labels and status wording.

---

### Phase 4: Telegram Search in Agents Experience — Remainder

**Status:** ~30% Complete

**Already done:**
- Backend `source` field on `ListSessionItem` schema and both GET/SSE session routes.
- Frontend filters sessions by `source === 'telegram'` client-side.

**Remaining work:**

**Files**
- Modify: `frontend/src/pages/AgentsPage.vue`
- Modify: `frontend/src/api/agent.ts`
- Optional: `backend/app/interfaces/api/session_routes.py` (add `source`, `q`, `status` query params)
- Optional: `backend/app/infrastructure/repositories/mongo_session_repository.py` (filtered query)

**Changes**
- Add search input and status filter dropdown to Agents tab sessions section.
- Option 1 (fast): client-side filter over already-fetched sessions.
- Option 2 (scalable): backend params `GET /sessions?source=telegram&q=<query>&status=<status>&limit=<n>`.
- Add result count badge (e.g., "12 sessions" → "3 of 12 sessions").

**Acceptance**
- User can find Telegram sessions by title/message/status quickly from `/chat/agents`.

---

### Phase 5: Observability and Guardrails

**Status:** Not Started

**Files**
- Modify: `backend/app/interfaces/api/channel_link_routes.py`
- Modify: `backend/app/domain/services/channels/message_router.py`
- Modify: `backend/app/core/prometheus_metrics.py` (or equivalent)

**Changes**
- Add counters:
  - `channel_link_code_generated_total{channel}`
  - `channel_link_redeemed_total{channel}`
  - `channel_link_redeem_failed_total{reason}` (expired, not_found, already_used)
- Add structured log fields for code lifecycle (never log raw code; log hash/prefix only).
- Optional per-user rate limiter for code generation endpoint.

**Acceptance**
- Link funnel is measurable and debuggable.

---

### Phase 6: Test and Verification Closure

**Status:** Not Started (P1 — AgentsPage spec fix should happen before merging current changes)

**Files**
- Modify: `frontend/src/pages/__tests__/AgentsPage.spec.ts`
- Add: `frontend/src/composables/__tests__/useTelegramLink.spec.ts`
- Add: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py` (if not added in Phase 1)

**Changes**

1. **Fix AgentsPage.spec.ts regression** (P1 — immediate):
   - Remove or update the test expecting `push('/chat/session-1')` on linked state.
   - Replace with tests for the new behavior:
     - Linked state renders "Telegram connected" badge and refresh button.
     - Unlinked state renders onboarding hero and the primary Telegram-link CTA (label aligned with current Phase 3 copy).
     - Sessions are filtered to `source === 'telegram'` only.

2. **Add composable tests** (`useTelegramLink.spec.ts`):
   - `generate()` calls API and sets `bindCommand`, `countdown`, starts polling.
   - `copyCommand()` writes to clipboard and sets `isCopied` for 2 seconds.
   - `openDeepLink()` prefers `deepLinkUrl` over `botUrl`.
   - Countdown reaching 0 calls `clearDraft('expired')`.
   - Polling detecting a linked channel calls `clearDraft('linked')` and `onLinkSuccess` callback.

3. **Add adapter command tests** (may be done in Phase 1):
   - `/start bind_ABC123` forwards to message bus with text `/start bind_ABC123`.
   - `/start` (no args) sends greeting reply, does not forward.
   - `/stop`, `/status`, `/link` forward via `_forward_command`.
   - Unknown `/foo` gets help hint reply.

**Acceptance**
- Frontend and backend tests explicitly cover the end-to-end link workflow and command routing.
- `bun run vitest src/pages/__tests__/AgentsPage.spec.ts --run` passes.

---

## Implementation Priority

| Priority | Phase | Status | Effort | Why |
|----------|-------|--------|--------|-----|
| **P0** | Phase 1 — Adapter command fix | Not Started | Medium | Unblocks the entire Telegram linking flow |
| **P1** | Phase 6 — Fix AgentsPage.spec.ts | Not Started | Small | Regression from completed work; blocks clean merge |
| **P1** | Phase 3 remainder — Route fix + shared card | ~70% Done | Medium | Completes UX consistency |
| **P2** | Phase 2 — Dev gateway | Not Started | Small | Dev experience improvement |
| **P2** | Phase 4 remainder — Search/filter UI | ~30% Done | Medium | Scalability for many sessions |
| **P3** | Phase 5 — Observability | Not Started | Small | Operations tooling |

---

## Verification Checklist

1. Backend lint/tests:
   - `conda activate pythinker && cd backend && ruff check .`
   - `conda activate pythinker && cd backend && ruff format --check .`
   - `conda activate pythinker && cd backend && pytest tests/integration/test_channel_integration.py tests/interfaces/api/test_channel_link_routes.py -p no:cov -o addopts=`
2. Frontend lint/tests:
   - `cd frontend && bun run lint`
   - `cd frontend && bun run type-check`
   - `cd frontend && bun run vitest src/pages/__tests__/AgentsPage.spec.ts --run`
3. Manual E2E (requires gateway running):
   - Generate link from Agents tab.
   - Complete deep-link start flow from Telegram.
   - Confirm link state updates without manual refresh.
   - Confirm Telegram session appears and is searchable in Agents tab.

---

## Risks and Mitigations

1. **Risk:** Changing `/start` behavior can affect greeting UX.
   - Mitigation: check `context.args` — if first arg starts with `bind_`, forward; else run existing greeting. Plain `/start` is unaffected.
2. **Risk:** Modifying vendored nanobot code creates maintenance burden.
   - Mitigation: mark each change with `# PYTHINKER-PATCH` comment; keep patches minimal and adapter-level only.
3. **Risk:** Running gateway in dev increases resource usage.
   - Mitigation: opt-in `--gateway` flag with clear messaging when omitted.
4. **Risk:** Search query params can impact session list performance.
   - Mitigation: add index and cap result size (`limit`), then paginate if needed.
5. **Risk:** AgentsPage.spec.ts regression ships if not fixed promptly.
   - Mitigation: prioritize spec fix (Phase 6 partial) alongside or before Phase 1.

---

## Definition of Done

1. Telegram deep link linking works with `/start bind_<CODE>` path end-to-end.
2. Telegram commands `/new`, `/stop`, `/status`, `/link` are functional from chat.
3. Dev workflow includes a clear, reproducible gateway startup path (`--gateway`).
4. Agents tab provides Telegram session search/filter.
5. AccountSettings, AgentSettings, and AgentsPage share one consistent link UX (composable + shared card).
6. Automated tests cover adapter command forwarding and frontend link/search behavior.
7. All existing tests pass (`AgentsPage.spec.ts` updated to match new behavior).
