# Telegram Full OpenClaw Parity Master Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close every known Telegram gap between Pythinker and the local `openclaw-main` reference, including native command UX, callback workflows, richer inbound context, outbound action coverage, and the OpenClaw dual-lane answer/reasoning streaming design.

**Architecture:** `openclaw-main` remains the behavioral source of truth, but parity must be translated into Pythinker’s architecture: Telegram ingress/egress lives in `backend/nanobot/channels/telegram.py`, routing lives in `backend/app/domain/services/channels/message_router.py`, and agent/runtime behavior lives in `backend/app/application/services/agent_service.py` plus the execution/tool stack. The key design constraint is that several remaining Telegram gaps are not transport-only. True parity requires upstream event-contract and session-state changes so Telegram can receive separate answer and reasoning lanes instead of a single generic text stream.

**Tech Stack:** Python 3.11, `python-telegram-bot`, asyncio, Pydantic v2, pytest, Ruff

---

## Priority Tiers

Not all workstreams carry equal weight. This tiering guides sequencing when time is constrained.

### Tier 1 — Must-have for meaningful parity (high user-facing impact)

- **Workstreams 5, 6, 7, 9** — Inbound context, outbound semantics, actions, command menu. Partially done in WIP.
- **Workstream 3** — Command-argument menus. High UX impact for Telegram users.

### Tier 2 — Required for true parity but architecturally heavy

- **Workstreams 1, 2** — Dual-lane streaming, reasoning visibility state. Core event contract changes.

### Tier 3 — Nice-to-have / niche

- **Workstream 4** — Model/provider buttons. Not a common Pythinker workflow.
- **Workstream 8** — Status/ack reactions. Cosmetic UX polish.
- **Workstream 10** — Forum topic binding. Niche use case.

Tier 1 can ship independently and delivers immediate value. Tier 2 is the hardest work and should be tackled after Tier 1 is committed and stable. Tier 3 items are optional and should not block a "materially improved" claim.

---

## Conscious Exclusions

The following OpenClaw behaviors are **intentionally excluded** from this parity effort, with rationale:

1. **Draft transport mode (`sendMessageDraft`)** — OpenClaw supports Telegram's undocumented `sendMessageDraft` API as an alternative streaming transport that shows typing-indicator-style previews. This API is undocumented, fragile, and adds complexity for marginal UX benefit. Pythinker uses message-mode previews only. If needed later, `draft-stream.ts` lines 119-301 document the full fallback behavior.

2. **Audio preflight transcription** — OpenClaw transcribes audio messages in groups to check for bot mentions before processing (`bot-message-context.ts` lines 430-457). Pythinker does not support audio-message transcription as an inbound path. This is a separate feature, not a parity gap.

3. **DM topic session isolation** — OpenClaw uses `resolveThreadSessionKeys()` to give each DM topic its own session namespace. Pythinker already separates sessions by DM thread/topic via routing keys. Full isolation parity would require session-storage changes that are out of scope.

4. **Dock commands** — OpenClaw dynamically creates `/dock_*` commands from channel dock configurations (`commands-registry.data.ts` lines 49-59). Pythinker has no dock/channel-switching concept.

---

## Source Of Truth

Use these `openclaw-main` files as the authoritative references while implementing the remaining work:

- Telegram transport and routing:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-handlers.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-message-context.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/helpers.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/send.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/delivery.send.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/delivery.replies.ts`
- Draft/preview and dual-lane delivery:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/draft-stream.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/lane-delivery.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/channels/draft-stream-controls.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/channels/draft-stream-loop.ts`
- Native commands, menus, and callback UX:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-native-commands.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-native-command-menu.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/model-buttons.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/commands-registry.data.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/commands-models.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/directive-handling.impl.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/get-reply-directives.ts`
- Telegram action/plugin layer:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/channels/plugins/actions/telegram.ts`
- Key OpenClaw tests to mirror behavior:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot.create-telegram-bot.test.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot.test.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/send.test.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/commands.test.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/agent-runner.runreplyagent.e2e.test.ts`

## Current Pythinker Status Snapshot

This section is intentionally factual. It is not a completion claim for full parity.

**Re-review note (2026-03-09):** This snapshot was refreshed against the current codebase and a passing Telegram-focused regression run:

```bash
conda run -n pythinker bash -lc 'cd backend && pytest -p no:cov -o addopts= tests/domain/services/channels/test_message_router.py tests/infrastructure/external/channels/test_telegram_channel_commands.py -q'
```

Result: `202 passed`

### Completed Or Close Enough

- Custom polling and webhook ownership are in place in `backend/nanobot/channels/telegram.py`, `backend/nanobot/channels/telegram_webhook.py`, and `backend/nanobot/channels/telegram_update_offset_store.py`.
- Allowed updates now cover `message`, `callback_query`, `channel_post`, and `message_reaction`.
- Offset persistence, update dedupe, DM/group/topic policy checks, account linking, and sender/topic session key routing are implemented.
- Inbound media metadata, sticker metadata, reply/thread identifiers, forwarded-message metadata, location metadata, and reply-media placeholders are preserved.
- Lane-aware stream plumbing exists in the event model and Telegram delivery path: separate answer/reasoning preview state, archived-preview consumption, regressive update blocking, generation tracking, and per-lane finalization are implemented.
- Session fields and text commands exist for `reasoning_visibility`, `thinking_level`, `verbose_mode`, and `elevated_mode`. `/models` also exists as a text command.
- Paginated `/help` and `/commands` menus exist with `commands_page_*` callback pagination, and custom primary commands can be registered into the Telegram command menu.
- Telegram-native outbound actions already supported in Pythinker:
  - `edit_text`
  - `edit_buttons`
  - `delete`
  - `react`
  - `poll`
  - `topic_create`
  - `sticker`
  - `pin`
  - `unpin`

### Partial Parity

- Reply context is only partial.
  - Pythinker preserves `reply_to_id`, `reply_to_body`, `reply_to_sender`, `reply_to_is_quote`, forwarded context, reply-media placeholders, and location context.
  - OpenClaw still goes further with thread starter context, bounded inbound history, and richer structured sender/conversation blocks.
- Native command UX is only partial.
  - Pythinker has paginated `/help` and `/commands`, text commands for `/reasoning`, `/think`, `/verbose`, `/elevated`, and `/models`, plus a command registry schema that now supports args, choices, scopes, and `args_menu`.
  - OpenClaw still has Telegram-native argument menus, callback-driven option toggles, and provider/model button workflows.
- Streaming is only partial.
  - Pythinker has lane-aware `StreamEvent`s and Telegram supports separate answer/reasoning preview lanes.
  - OpenClaw still has end-to-end answer/reasoning split across the full runtime plus enforced reasoning visibility/session controls.
- Session-option parity is only partial.
  - Pythinker persists `reasoning_visibility`, `thinking_level`, `verbose_mode`, and `elevated_mode`.
  - The main runtime and Telegram delivery path do not yet obey those settings consistently.
- Suggestion follow-up handling is only partial.
  - Callback parsing for historic `telegram:followup:*` payloads still exists.
  - The router currently suppresses Telegram suggestion-button rendering, so this is not an active parity feature.
- Outbound send semantics are only partial.
  - Pythinker now supports `quote_text`, reply-to-first/all, thread fallback, and dual-lane preview finalization behavior.
  - OpenClaw still has broader chunk-aware follow-up send behavior, fuller voice fallback semantics, and more exact delivery-state parity.
- Telegram actions exist but are not architecturally complete.
  - Pythinker has bounded action envelopes, normalization, discovery, and channel dispatch for `edit_text`, `edit_buttons`, `delete`, `react`, `poll`, `topic_create`, `sticker`, `pin`, and `unpin`.
  - OpenClaw still has a broader shared action adapter, account-aware gating, sticker search, and status-reaction integration.

### Not Yet Implemented

- End-to-end dual-lane answer/reasoning runtime parity across the main execution and summarization paths.
- Delivery-side enforcement of `reasoning_visibility` (`off`, `on`, `stream`).
- Command-argument inline menus.
- Telegram model/provider button workflows.
- Thread starter and pending history prompt context parity.
- Status/ack reaction parity.
- Unified Telegram action adapter comparable to OpenClaw’s plugin layer.
- Change-hashed / overflow-aware native command menu sync and collision handling.
- Persistent topic/session bindings beyond routing keys.

## What “Full Parity” Means In Practice

Pythinker should only be considered at full Telegram parity when all of the following are true:

1. Telegram receives the same *kind* of inbound context that OpenClaw prepares.
2. Telegram users can drive session options and navigation through the same native slash-command and callback patterns.
3. Telegram outbound delivery respects the same first-chunk reply/button/quote semantics, media fallback rules, and edit rules.
4. Telegram can show an answer preview lane and a reasoning preview lane independently, with OpenClaw-style reasoning session controls.
5. The remaining Telegram action surface is not a bespoke one-off path but a stable app-level contract.

## Hard Architectural Gaps Blocking Full Parity

These are the non-negotiable gaps that must be resolved before the remaining Telegram work can be “just transport”.

### 1. Lane-Aware Events Exist, But Main Runtime Split Is Incomplete

Pythinker now has `lane` on `StreamEvent`, Telegram preserves lane metadata, and the Telegram channel maintains separate preview state per lane. The remaining gap is that the main runtime still does not emit a true OpenClaw-style answer/reasoning split consistently across execution and summarization.

Implication:
- Telegram dual-lane delivery is only partially real until the runtime emits both lanes intentionally instead of falling back to the default `answer` lane for most output.

### 2. Persisted Reasoning Visibility State Exists, But Delivery Does Not Obey It

Pythinker now persists Telegram-native session fields for `reasoning_visibility`, `thinking_level`, `verbose_mode`, and `elevated_mode`. The remaining gap is that Telegram delivery and the main chat/runtime path do not yet enforce those settings.

Implication:
- Users can store Telegram option state today, but that state is not yet a reliable source of truth for runtime or delivery behavior.

### 3. No Central Callback Namespace For Rich Telegram UX

Pythinker currently handles:
- `commands_page_*`
- `telegram:followup:*`
- generic callback passthrough

OpenClaw has multiple structured callback families for models, command-argument menus, and navigation. Pythinker needs the same callback discipline instead of expanding ad hoc callback handling in one file forever.

## Remaining Workstreams

The remaining parity work is grouped below in the order that actually reduces risk.

### Workstream 1: Introduce A Dual-Lane Telegram Streaming Contract

**Status:** In Progress

**Why it matters:** This is still the biggest remaining gap. Pythinker now has lane-aware infrastructure, but it does not yet deliver a fully faithful OpenClaw answer/reasoning split end-to-end.

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/lane-delivery.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/draft-stream.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/dispatch-from-config.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/agent-runner.runreplyagent.e2e.test.ts`

**Pythinker files likely touched:**
- `backend/app/domain/models/event.py`
- `backend/app/application/services/agent_service.py`
- `backend/app/domain/services/agents/execution.py`
- `backend/app/domain/services/channels/message_router.py`
- `backend/nanobot/channels/telegram.py`
- `backend/tests/unit/agents/test_execution.py`
- `backend/tests/domain/services/channels/test_message_router.py`
- `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Required behavior:**
- Stream events must declare a lane or equivalent semantic channel:
  - `answer`
  - `reasoning`
- Telegram must maintain separate preview state per lane.
- Final answer delivery must not destroy reasoning state incorrectly.
- Boundary rotation rules from OpenClaw must be mirrored:
  - previous preview may be archived
  - a finalized preview may remain visible
  - superseded previews may be deleted

**Current progress in Pythinker:**
- `StreamEvent` already declares `lane`.
- planner/runtime code can emit `lane="reasoning"` in some paths.
- router preserves lane for Telegram and suppresses reasoning lane for non-Telegram channels.
- Telegram preview state already supports archived-preview consumption, regressive update blocking, generation tracking, and per-lane finalization.

**What still remains:**
- Main execution/summarization paths still do not emit a full OpenClaw-style answer/reasoning split consistently.
- Delivery result types are not yet formalized into a stable app-level contract.

**Critical OpenClaw behaviors to replicate (verified against source):**

1. **Archived preview consumption** (`lane-delivery.ts` lines 317-359): When a lane boundary rotates, the old preview message is not immediately deleted. Instead, the final send for the new boundary can **consume** the archived preview (edit it in-place) rather than sending a new message. This avoids message-count churn. The `deleteIfUnused` flag controls whether an unconsumed archived preview is cleaned up.

2. **Regressive update blocking** (`lane-delivery.ts` lines 123-138): OpenClaw prevents editing a preview to shorter content. If a streaming chunk would shrink the visible text (e.g., from 500 chars back to 100), the edit is skipped. This prevents visual flicker during bursty streaming.

3. **Generation tracking for superseded previews** (`draft-stream.ts` lines 207-214): A `generation` counter increments on `forceNewMessage()`. Late-arriving sends from old generations trigger `onSupersededPreview()` instead of overwriting the current preview. This prevents race conditions during boundary rotation.

4. **Per-lane finalization tracking** (`lane-delivery.ts` line 59): `finalizedPreviewByLane: Record<LaneName, boolean>` — different lanes finalize at different times. The answer lane may be final while reasoning is still streaming.

5. **Delivery result types** (`lane-delivery.ts` line 21): Each delivery returns `"preview-finalized" | "preview-updated" | "sent" | "skipped"` so the caller can react to the outcome.

**Design decision to mirror OpenClaw:**
- Non-Telegram channels can continue to suppress reasoning payloads.
- Telegram gets the dedicated split path.

**Recommended sub-task breakdown** (this workstream is the largest):
- 1a: Add `lane` field to `StreamEvent` in `event.py` (default `"answer"` for backward compat)
- 1b: Tag reasoning stream chunks in `execution.py` (when LLM emits reasoning tokens)
- 1c: Route lane-tagged events in `message_router.py` (preserve lane for Telegram, suppress reasoning for other channels)
- 1d: Build per-lane `_TelegramPreviewState` in `telegram.py` with archived-preview and generation tracking

### Workstream 2: Add Reasoning Visibility State And Telegram Controls

**Status:** In Progress

**Why it matters:** OpenClaw’s second lane is useful because users can control it with `/reasoning off|on|stream`. Pythinker now has persisted state and text commands, but delivery behavior still ignores that state.

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/thinking.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/directive-handling.impl.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/get-reply-directives.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/commands-registry.data.ts`

**Pythinker files likely touched:**
- `backend/app/application/services/agent_service.py`
- `backend/app/domain/services/channels/message_router.py`
- `backend/app/domain/services/agents/execution.py`
- `backend/app/domain/services/command_registry.py`
- `backend/nanobot/channels/telegram.py`
- `backend/tests/domain/services/channels/test_message_router.py`
- `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Required behavior:**
- Persist Telegram-visible reasoning mode per session:
  - `off`
  - `on`
  - `stream`
- Add `/reasoning` command and alias support.
- Add Telegram-native command argument menu for `/reasoning` when no arg is provided.
- Make lane delivery obey session state:
  - `off`: no reasoning lane visible
  - `on`: reasoning available but not live-streamed
  - `stream`: reasoning lane streams live

**Current progress in Pythinker:**
- Session fields now exist for `reasoning_visibility`, `thinking_level`, `verbose_mode`, and `elevated_mode`.
- `/reasoning`, `/think`, `/verbose`, `/elevated`, and `/models` text commands are implemented.

**What still remains:**
- No Telegram-native argument menu is shown when `/reasoning` is invoked without an argument.
- Lane delivery does not yet obey `off|on|stream`.
- The main chat/runtime path does not yet apply the stored session options consistently.

**Important note:** This is not the same as Pythinker’s current `thinking_mode`. `thinking_mode` chooses runtime effort. OpenClaw’s `reasoning` setting controls visibility of reasoning output.

**Design boundary:** The `"stream"` value is Telegram-specific. OpenClaw’s `directive-handling.impl.ts` line 397 explicitly says "Reasoning stream enabled (Telegram only)." This means the `"stream"` reasoning level is a transport-visibility concern, not a universal agent concern. The state should be stored per-session but the `"stream"` behavior is only consumed by the Telegram delivery path.

**Persistence target:** Reasoning visibility state should be stored in the session document (likely via `agent_session_lifecycle.py` or a new field on the session model), not in channel-specific storage.

### Workstream 3: Build Command-Argument Menus And Callback-Driven Option Toggles

**Status:** In Progress

**Why it matters:** OpenClaw does not force users to memorize every option string. Telegram native commands open button menus for arguments when possible.

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-native-commands.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/commands-registry.data.ts`

**OpenClaw behaviors to port:**
- command args with `choices`
- `argsMenu: "auto"`
- inline keyboard generation for command args
- callback payloads that reconstruct the final slash command

**Pythinker files likely touched:**
- `backend/app/domain/services/command_registry.py`
- `backend/nanobot/channels/telegram.py`
- `backend/app/domain/services/channels/message_router.py`
- tests in both router and Telegram channel suites

**Minimum full-parity command set to support:**
- `/reasoning`
- `/think`
- `/verbose`
- `/elevated`
- `/models`
- any additional custom command that can expose `choices`

**Current progress in Pythinker:**
- The command registry now supports typed args, choices, `args_menu`, and `scope`.
- Telegram can register custom primary commands from the shared registry into the bot command menu.

**Current blocker:** Telegram does not yet consume the richer registry schema to render argument menus or reconstruct slash commands from callback taps.

**Command scope system** (missing from original plan): OpenClaw commands have a `scope` field (`"native" | "text" | "both"`) that controls where a command is available:
- `native`: Only registered as a Telegram bot menu command
- `text`: Only matched as `/command` in message body text
- `both`: Registered in both paths

Validation rules differ per scope (`commands-registry.data.ts` lines 81-124). Without scope awareness, commands may appear incorrectly in the Telegram menu or conflict with text-based parsing.

### Workstream 4: Add Telegram Model/Provider Button Workflows

**Status:** Not Started

**Why it matters:** OpenClaw has a complete Telegram-native model browsing flow with callback data compression and provider/model pagination.

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/model-buttons.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/commands-models.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/directive-handling.model.ts`

**Pythinker files likely touched:**
- `backend/nanobot/channels/telegram.py`
- `backend/app/domain/services/channels/message_router.py`
- model/session settings layer under `backend/app`
- Telegram tests

**Required parity items:**
- provider keyboard
- model keyboard with page buttons
- callback parsers
- callback-data length safety
- current-model indicator
- provider ambiguity handling
- `/models` and possibly `/model` parity

**Provider ambiguity resolution detail** (`model-buttons.ts` lines 103-144): When `mdl_sel_{provider}/{model}` exceeds 64 bytes, OpenClaw falls back to compact form `mdl_sel/{model}` (provider omitted). On selection, the provider must be resolved from the model catalog. If the same model name exists under multiple providers, OpenClaw returns `{ kind: "ambiguous", matchingProviders }` and asks the user to pick a provider. Pythinker must handle this edge case or cap model names to avoid the compact fallback entirely.

**Note:** The user previously said model switching is not a common Pythinker workflow. That affects priority, not parity status. For true parity this remains unfinished work. **Priority: Tier 3.**

### Workstream 5: Complete Inbound Message Context Parity

**Status:** Partial

**What already exists in Pythinker:**
- basic sender identifiers
- thread/topic metadata
- reply quote/body metadata
- media attachment metadata
- forwarded-message context
- reply target media placeholders
- location/venue context

**What OpenClaw still does that Pythinker does not:**
- thread starter body
- pending history context between replies
- richer structured sender/conversation context blocks in the prompt

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-message-context.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/helpers.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/auto-reply/reply/inbound-meta.ts`

**Pythinker files likely touched:**
- `backend/nanobot/channels/telegram.py`
- `backend/app/domain/services/channels/message_router.py`
- maybe session/history persistence code under `backend/app`
- tests in `test_message_router.py` and `test_telegram_channel_commands.py`

**Required parity outcome:**
- The agent prompt should receive explicit trusted and untrusted context blocks for:
  - conversation info
  - sender info
  - replied message
  - forwarded message context
  - thread starter
  - bounded inbound history

### Workstream 6: Match OpenClaw Outbound Reply Semantics

**Status:** Partial

**What Pythinker has now:**
- reply-to-first/all modes
- message-thread fallback
- text/media send paths
- PDF fallback path
- explicit `quote_text` support on outbound send
- first-chunk-only reply application for normal text chunking
- markdown-to-Telegram HTML rendering
- preview finalization against the final answer lane

**What OpenClaw still does better:**
- chunk-aware follow-up text sends after media
- voice-message fallback semantics
- more exact delivery progress tracking

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/send.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/delivery.send.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/delivery.replies.ts`

**Pythinker files likely touched:**
- `backend/nanobot/channels/telegram.py`
- `backend/app/domain/services/tools/message.py`
- `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Notable current gaps in Pythinker tool contract:**
- The core send contract still does not model all OpenClaw delivery outcomes and follow-up behaviors as first-class concepts.

### Workstream 7: Expand Telegram Action Surface Into A Stable App Contract

**Status:** Partial

**What Pythinker has now:**
- action envelope types in `backend/app/domain/services/tools/message.py`
- dispatch support in `backend/nanobot/channels/telegram.py`
- action discovery via `list_supported_actions()`
- support for `pin` and `unpin`

**What is still missing versus OpenClaw:**
- one unified Telegram action adapter boundary
- richer send action options
- account-aware action gating
- sticker search flow
- reaction/status integration
- consolidated validation rules shared across command/tool/callback paths

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/channels/plugins/actions/telegram.ts`

**Pythinker files likely touched:**
- `backend/app/domain/services/tools/message.py`
- `backend/app/domain/services/agents/execution.py`
- `backend/nanobot/channels/telegram.py`
- possibly a new adapter module under `backend/app` or `backend/nanobot`

**Required parity outcome:**
- Telegram actions should no longer feel like special-case metadata passed through one tool path only.
- They should be a first-class adapter contract usable by tools, commands, and callback handlers.

### Workstream 8: Add Status/Ack Reaction Parity

**Status:** Not Started — **Priority: Tier 3**

**Why it matters:** OpenClaw uses reaction semantics as part of the Telegram UX. Pythinker currently supports inbound reaction events and outbound explicit `react` action, but not the broader status/ack reaction behavior around delivery state.

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-message-context.ts` (lines 548-635)
- related reaction/status helpers imported there

**OpenClaw StatusReactionController detail** (previously underspecified):

OpenClaw implements a full state-machine for lifecycle reactions via `createStatusReactionController()`:
- **States:** idle → processing (thinking emoji) → completed (checkmark) or errored (cross)
- **Adapter pattern:** The controller takes a `setReaction` adapter function, decoupling it from the Telegram API
- **Coordination with delivery:** The ACK reaction is set when processing starts and removed/replaced after the reply is delivered (`removeAckAfterReply` flag)
- **Scope gating:** Status reactions are only enabled when `statusReactionsEnabled` is true for the account

**Pythinker implementation approach:**
- Add a `StatusReactionController` class to `backend/nanobot/channels/telegram.py`
- Hook into the message processing lifecycle (pre-agent, post-agent, on-error)
- Gate behind a feature flag (`telegram_status_reactions_enabled`)

**Pythinker files likely touched:**
- `backend/nanobot/channels/telegram.py`
- `backend/app/domain/services/channels/message_router.py`
- maybe agent lifecycle hooks or delivery policy

### Workstream 9: Match OpenClaw Native Command Menu Management

**Status:** Partial

**What Pythinker has now:**
- Telegram command registration
- paginated `/help`
- `/commands` alias
- custom primary commands from the shared command registry can be added to the Telegram menu

**What OpenClaw still has that Pythinker does not:**
- change-hashed command menu sync to avoid rate limits
- overflow-aware menu capping with issue reporting
- plugin/custom/native command collision handling at menu-build time
- a richer command catalog

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-native-command-menu.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-native-commands.ts`

**Pythinker files likely touched:**
- `backend/nanobot/channels/telegram.py`
- `backend/app/domain/services/command_registry.py`
- startup tests

### Workstream 10: Complete Forum Topic And Session Binding Parity

**Status:** Partial

**What Pythinker already has:**
- `message_thread_id`
- forum topic routing keys
- topic create outbound action
- session key separation by DM thread/topic
- forum-topic and DM-thread aware inbound policy routing

**What remains versus OpenClaw:**
- persistent thread/topic bindings with richer session meta
- explicit ACP-like thread target routing patterns
- quote and thread-starter interaction with topic routing
- broader command routing through configured topic bindings

**Reference files:**
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-native-commands.session-meta.test.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-message-context.ts`

## Ordered Implementation Plan

The work should be done in this order. The order is about dependency management, not convenience.

### Task 0: Stabilize And Truth-Check The Parity Baseline

**Status:** Historical prerequisite mostly complete

**Current note:** The original “large uncommitted WIP” prerequisite is stale. Re-review on 2026-03-09 found that most of that transport baseline has already landed in the codebase and is covered by passing Telegram tests. Current local uncommitted changes should still be reviewed independently before additional parity work lands.

**Current baseline covers:**
- `/commands` alias and paginated `/help` with callback pagination
- Reply context extraction (quote, external_reply, media placeholders)
- Forwarded and location context extraction
- `delivery_metadata` on `MessageEvent`
- Full action dispatch (edit/delete/react/poll/topic/sticker/pin/unpin)
- Button and action normalization in `message.py`
- lane-aware preview delivery behavior with archived-preview coverage
- broad Telegram router/channel regression coverage

**Deliverable:**
- Atomic commits per concern (tests, router, telegram, message tool, event model)
- All tests pass, lint clean

### Task 1: Upgrade The Event And Session Contract For Dual-Lane Streaming

**Priority: Tier 2**

**Files:**
- Modify: `backend/app/domain/models/event.py`
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/domain/services/agents/execution.py`
- Modify: `backend/app/domain/services/channels/message_router.py`
- Test: `backend/tests/unit/agents/test_execution.py`
- Test: `backend/tests/domain/services/channels/test_message_router.py`

**Sub-tasks:**
- 1a: Add `lane: str = "answer"` field to `StreamEvent` in `event.py` (backward compatible default)
- 1b: Tag reasoning stream chunks in `execution.py` with `lane="reasoning"` when LLM emits reasoning tokens
- 1c: Route lane-tagged events in `message_router.py` — preserve lane for Telegram, suppress `reasoning` lane for other channels
- 1d: Build per-lane `_TelegramPreviewState` in `telegram.py` with archived-preview consumption and generation tracking

**Deliverable:**
- stream events distinguish `answer` versus `reasoning`
- router preserves lane metadata for Telegram
- regressive update blocking prevents visual flicker
- archived preview consumption avoids message churn

### Task 2: Add Persisted Telegram Reasoning Visibility State

**Files:**
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/domain/services/channels/message_router.py`
- Modify: session/state persistence code under `backend/app`
- Test: reasoning/session tests to add

**Deliverable:**
- `off|on|stream` reasoning state exists independently of `thinking_mode`

### Task 3: Rebuild Telegram Preview Delivery Around Two Lanes

**Files:**
- Modify: `backend/nanobot/channels/telegram.py`
- Possibly create: `backend/nanobot/channels/telegram_lane_delivery.py`
- Test: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Deliverable:**
- separate preview state for answer and reasoning
- archived/finalized preview semantics comparable to OpenClaw

### Task 4: Expand Command Registry Schema For Argument Menus

**Files:**
- Modify: `backend/app/domain/services/command_registry.py`
- Modify: Telegram command/menu code in `backend/nanobot/channels/telegram.py`
- Test: Telegram command and callback tests

**Deliverable:**
- command definitions can declare args, choices, and menu metadata

### Task 5: Implement Telegram-Native Option Commands

**Files:**
- Modify: `backend/nanobot/channels/telegram.py`
- Modify: `backend/app/domain/services/channels/message_router.py`
- Modify: any user/session settings layer needed
- Test: command/callback parity tests

**Deliverable:**
- `/reasoning`
- `/think`
- `/verbose`
- `/elevated`

### Task 6: Implement Provider/Model Button Flows

**Files:**
- Modify: Telegram callback/menu path
- Modify: model/session settings layer
- Test: provider/model callback tests

**Deliverable:**
- provider list
- model list
- callback-based selection
- pagination

### Task 7: Finish Inbound Context Parity

**Files:**
- Modify: `backend/nanobot/channels/telegram.py`
- Modify: `backend/app/domain/services/channels/message_router.py`
- Test: reply/forward/history/location context tests

**Deliverable:**
- forwarded context
- reply media context
- location context
- thread starter
- bounded inbound history

### Task 8: Expand Outbound Send Contract

**Files:**
- Modify: `backend/app/domain/services/tools/message.py`
- Modify: `backend/nanobot/channels/telegram.py`
- Test: send semantics tests

**Deliverable:**
- `quoteText`
- first-chunk-only buttons/quote semantics
- richer follow-up send semantics

### Task 9: Consolidate Telegram Actions Into A Stable Adapter

**Files:**
- Modify/Create: Telegram action adapter under `backend/app` or `backend/nanobot`
- Modify: `backend/app/domain/services/tools/message.py`
- Modify: execution/runtime tool handling
- Test: action adapter tests

**Deliverable:**
- send/edit/delete/react/poll/topic/sticker/search unified contract

### Task 10: Final Verification And Gap Closure Review

**Files:**
- Add/expand: integration and regression tests

**Deliverable:**
- parity checklist passes
- remaining gap list is empty or explicitly documented

## Verification Matrix

Full parity should not be claimed until all of the following exist:

- Unit tests for lane-aware events and reasoning state.
- Router tests for dual-lane Telegram outbounds.
- Telegram channel tests for:
  - answer lane preview
  - reasoning lane preview
  - preview rotation with archived-preview consumption
  - regressive update blocking
  - generation tracking for superseded previews
  - per-lane finalization independence
  - finalization rules
  - callback argument menus
  - `/reasoning`, `/think`, `/verbose`, `/elevated`, `/models`
  - provider/model pagination callbacks
  - forwarded/reply/history context
  - quote-text send semantics
  - status/ack reactions (Tier 3 — may be deferred)
- A broader regression run at minimum:

```bash
conda run -n pythinker bash -lc 'cd backend && pytest -p no:cov -o addopts= tests/unit/agents/test_execution.py tests/domain/services/channels/test_message_router.py tests/domain/services/channels/test_telegram_delivery_policy.py tests/infrastructure/external/channels/test_telegram_channel_commands.py -q'
```

- Lint and format checks on touched files:

```bash
conda run -n pythinker bash -lc 'cd backend && ruff check . && ruff format --check .'
```

## Final Definition Of Done

Pythinker has full Telegram parity with `openclaw-main` only when:

- Telegram command UX is callback-native and option-complete.
- Telegram inbound context contains the same meaningful context classes.
- Telegram outbound delivery matches OpenClaw’s first-chunk and quote semantics.
- Telegram reasoning behavior is lane-aware and session-controlled.
- The parity checklist above has no remaining “partial” or “not started” items.

Until then, the correct status is:
- Telegram parity is materially improved.
- Telegram full OpenClaw parity is still incomplete.

## Amendments Log

**2026-03-09 — Re-review progress refresh (current codebase + tests):**

1. Refreshed **Current Pythinker Status Snapshot** from the actual current tree instead of the earlier WIP assumptions
2. Added a **Re-review note** with the latest passing Telegram-focused regression command and result (`202 passed`)
3. Moved Workstreams **1, 2, and 3** from `Not Started` to `In Progress`
4. Updated the snapshot to reflect shipped items that were previously undercounted: lane-aware preview infrastructure, persisted Telegram option fields, forwarded/location context, `quote_text`, and `pin`/`unpin`
5. Corrected the suggestion-button note: callback parsing remains, but Telegram suggestion rendering is currently suppressed in the router
6. Rewrote the stale **Hard Architectural Gaps** entries for dual-lane events and reasoning visibility to describe the current partial implementation accurately
7. Replaced the old **Task 0** WIP prerequisite note with a factual historical-status note so the plan no longer claims a large uncommitted baseline that has already mostly landed

**2026-03-08 — Post-review amendments (verified against OpenClaw source):**

1. Added **Priority Tiers** section — Tier 1 (transport, immediate value), Tier 2 (architectural, event contract), Tier 3 (nice-to-have)
2. Added **Conscious Exclusions** section — draft transport, audio transcription, DM topic isolation, dock commands
3. **Workstream 1** — Added 5 critical OpenClaw behaviors: archived preview consumption, regressive update blocking, generation tracking, per-lane finalization, delivery result types. Added recommended sub-task breakdown (1a-1d)
4. **Workstream 2** — Added design boundary note ("stream" is Telegram-specific per OpenClaw source line 397). Identified persistence target (session document)
5. **Workstream 3** — Added command scope system (`native | text | both`) from `commands-registry.data.ts`
6. **Workstream 4** — Added provider ambiguity resolution detail from `model-buttons.ts` compact fallback
7. **Workstream 8** — Expanded StatusReactionController detail (state machine, adapter pattern, scope gating). Added implementation approach
8. Added **Task 0** — Commit and stabilize existing WIP (+1,727 lines) before starting Tier 2 work
9. **Task 1** — Added sub-task breakdown (1a-1d) and expanded deliverables
10. **Verification Matrix** — Added archived-preview, regressive blocking, generation tracking, per-lane finalization test requirements
