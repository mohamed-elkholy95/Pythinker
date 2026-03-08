# Telegram OpenClaw Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring Pythinker's Telegram experience materially closer to `openclaw-main` by adopting its configuration contract, preview-streaming lifecycle, routing/threading model, and outbound delivery ergonomics, while preserving Pythinker's app gateway architecture.

**Architecture:** `openclaw-main` is the source of truth for Telegram behavior, but it cannot be copied verbatim because Pythinker routes Telegram through `backend/app` `MessageRouter` + `NanobotGateway` before delivery reaches `backend/nanobot/channels/telegram.py`. The implementation should port the OpenClaw design at the contract level: OpenClaw-like config surface, preview lifecycle, message-id tracking, edit/finalize fallback rules, and thread-aware routing. The first executable slice should land core preview streaming and config plumbing; subsequent slices should add broader parity items such as webhook transport, topic/thread handling, richer command/callback behavior, and policy controls.

**Tech Stack:** Python 3.12, Pydantic v2, python-telegram-bot, Pythinker app gateway, nanobot channel manager, pytest

---

## Source of Truth

Use these `openclaw-main` files as the authoritative reference during implementation:

- Config contract:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/config/types.telegram.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/config/discord-preview-streaming.ts`
- Telegram runtime/bootstrap:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/extensions/telegram/src/channel.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/monitor.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/webhook.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot.ts`
- Streaming and preview finalization:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-message-dispatch.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/draft-stream.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/lane-delivery.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/channels/draft-stream-loop.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/channels/draft-stream-controls.ts`
- Routing/threading/helpers:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-message-context.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/helpers.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/thread-bindings.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/targets.ts`
- Outbound send/edit behavior:
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/send.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/delivery.ts`
  - `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/delivery.replies.ts`

## Current-State Gap Summary

Pythinker today:

- Uses only long polling in `backend/nanobot/channels/telegram.py`.
- Routes real Telegram conversations through `backend/app/infrastructure/external/channels/nanobot_gateway.py` and `backend/app/domain/services/channels/message_router.py`.
- Buffers Telegram replies in final-only mode by default.
- Converts `progress` events into empty watchdog heartbeats.
- Does not emit Telegram preview edits, track preview message IDs, or finalize previews into edited final messages.
- Does not currently use `StreamEvent` for Telegram delivery even though the app agent stack emits them.

OpenClaw source-of-truth behavior:

- Exposes a normalized Telegram streaming config contract.
- Creates preview streams with throttling/debouncing.
- Tracks preview message IDs/draft IDs and can edit, materialize, or delete previews.
- Finalizes preview text intelligently and falls back to normal sends when final delivery is media-heavy, oversized, or otherwise ineligible for edit-in-place.
- Has more complete thread/topic routing, webhook support, inline-button handling, native command integration, and delivery abstractions.

## Priority Order

Implement in this order:

1. Preview streaming contract and delivery path.
2. Telegram config parity for the implemented streaming behavior.
3. Thread/reply message identity cleanup.
4. Delivery abstraction cleanup and richer fallback behavior.
5. Broader Telegram parity opportunities from OpenClaw.

## Non-Goals for the First Executable Slice

Do not attempt all of these in the first implementation pass:

- Multi-account Telegram support.
- OpenClaw-style answer/reasoning dual-lane preview parity.
- Telegram reactions/action tools/sticker feature parity.
- Full webhook migration.

Those remain planned parity opportunities and are listed later in this document.

### Task 1: Add the OpenClaw-Aligned Telegram Config Surface

**Files:**
- Modify: `backend/nanobot/config/schema.py`
- Modify: `backend/app/core/config_channels.py`
- Modify: `backend/app/interfaces/gateway/gateway_runner.py`
- Modify: `backend/app/infrastructure/external/channels/nanobot_gateway.py`
- Test: `backend/tests/core/test_config_channels.py`
- Test: `backend/tests/infrastructure/external/channels/test_nanobot_gateway.py`

**Step 1: Write the failing tests**

Add tests that assert the new Telegram settings exist and are wired end-to-end:

```python
def test_telegram_streaming_defaults(self, settings):
    assert settings.telegram_streaming == "partial"
    assert settings.telegram_streaming_throttle_seconds == 1.0
    assert settings.telegram_streaming_min_initial_chars == 30

def test_gateway_passes_telegram_streaming_settings(self, mock_router):
    gw = NanobotGateway(
        message_router=mock_router,
        telegram_token="123:FAKE",
        telegram_allowed=["*"],
        telegram_streaming="partial",
        telegram_streaming_throttle_seconds=1.25,
        telegram_streaming_min_initial_chars=45,
    )
    telegram_cfg = mock_channel_manager.call_args.args[0].channels.telegram
    assert telegram_cfg.streaming == "partial"
    assert telegram_cfg.streaming_throttle_seconds == 1.25
    assert telegram_cfg.streaming_min_initial_chars == 45
```

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/core/test_config_channels.py tests/infrastructure/external/channels/test_nanobot_gateway.py -q
```

Expected: FAIL because the new settings do not exist yet.

**Step 3: Write minimal implementation**

Add these fields:

- `backend/app/core/config_channels.py`
  - `telegram_streaming: str = "partial"`
  - `telegram_streaming_throttle_seconds: float = 1.0`
  - `telegram_streaming_min_initial_chars: int = 30`
- `backend/nanobot/config/schema.py`
  - `streaming: Literal["off", "partial", "block", "progress"] = "partial"`
  - `streaming_throttle_seconds: float = 1.0`
  - `streaming_min_initial_chars: int = 30`
- Pass the three values through `gateway_runner.py` into `NanobotGateway`, then into `TelegramConfig`.

**Step 4: Run tests to verify they pass**

Run the same command from Step 2.

Expected: PASS

**Step 5: Commit**

```bash
git add backend/nanobot/config/schema.py backend/app/core/config_channels.py backend/app/interfaces/gateway/gateway_runner.py backend/app/infrastructure/external/channels/nanobot_gateway.py backend/tests/core/test_config_channels.py backend/tests/infrastructure/external/channels/test_nanobot_gateway.py
git commit -m "feat: add telegram streaming config plumbing"
```

### Task 2: Teach MessageRouter to Forward Telegram Stream Events Instead of Dropping Them

**Files:**
- Modify: `backend/app/domain/services/channels/message_router.py`
- Test: `backend/tests/domain/services/channels/test_message_router.py`

**Step 1: Write the failing tests**

Add tests covering the new contract:

```python
async def test_telegram_streaming_emits_preview_outbounds_before_final():
    agent_svc = _make_agent_service(events=[
        StreamEvent(content="Thinking", is_final=False, phase="thinking"),
        StreamEvent(content=" more", is_final=False, phase="thinking"),
        _DynamicMessageEvent("Final answer"),
    ])
    router = MessageRouter(
        agent_svc,
        repo,
        telegram_final_delivery_only=True,
        telegram_streaming="partial",
    )
    replies = [r async for r in router.route_inbound(_make_inbound("Run task"))]
    assert replies[0].metadata["_progress"] is True
    assert replies[0].metadata["_telegram_stream"] is True
    assert replies[-1].content == "Final answer"

async def test_telegram_streaming_off_preserves_existing_final_only_behavior():
    ...
```

**Step 2: Run test to verify it fails**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/channels/test_message_router.py -q
```

Expected: FAIL because `stream` events are currently ignored.

**Step 3: Write minimal implementation**

Make these changes:

- Extend `_OUTBOUND_EVENT_TYPES` to include `"stream"` for Telegram handling.
- Add `telegram_streaming: str = "partial"` to `MessageRouter.__init__`.
- Add helper:

```python
def _telegram_streaming_enabled(self, channel: ChannelType) -> bool:
    return channel == ChannelType.TELEGRAM and self._telegram_streaming != "off"
```

- In `route_inbound()`:
  - keep final-only buffering for `message`/`report`;
  - do not buffer `stream` events when Telegram streaming is enabled;
  - continue swallowing empty `progress` heartbeat events.
- In `_event_to_outbound()` convert `StreamEvent` to:

```python
return OutboundMessage(
    channel=source.channel,
    chat_id=source.chat_id,
    content=event.content,
    reply_to=source.id,
    metadata={
        "_progress": True,
        "_telegram_stream": True,
        "_telegram_stream_phase": event.phase,
        "_telegram_stream_final": event.is_final,
    },
)
```

**Step 4: Run tests to verify they pass**

Run the command from Step 2.

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/channels/message_router.py backend/tests/domain/services/channels/test_message_router.py
git commit -m "feat: route telegram stream events through message router"
```

### Task 3: Implement OpenClaw-Style Preview Message Lifecycle in TelegramChannel

**Files:**
- Modify: `backend/nanobot/channels/telegram.py`
- Test: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Step 1: Write the failing tests**

Add channel-level tests for preview creation, edit, finalize, and fallback:

```python
@pytest.mark.asyncio
async def test_progress_preview_creates_then_edits_single_message():
    await channel.send(OutboundMessage(..., content="Hello", metadata={"_progress": True, "_telegram_stream": True}))
    await channel.send(OutboundMessage(..., content=" world", metadata={"_progress": True, "_telegram_stream": True}))
    bot.send_message.assert_awaited_once()
    bot.edit_message_text.assert_awaited_once()

@pytest.mark.asyncio
async def test_final_text_edits_existing_preview_instead_of_sending_new_message():
    ...

@pytest.mark.asyncio
async def test_media_or_pdf_final_clears_preview_and_uses_existing_delivery_path():
    ...

@pytest.mark.asyncio
async def test_streaming_off_skips_preview_logic():
    ...
```

**Step 2: Run test to verify it fails**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -q
```

Expected: FAIL because preview state and edit helpers do not exist.

**Step 3: Write minimal implementation**

Use OpenClaw’s `draft-stream.ts` / `lane-delivery.ts` as the behavioral reference, adapted to PTB:

- Add a small internal preview state object in `TelegramChannel`, for example:

```python
@dataclass
class _TelegramPreviewState:
    content: str = ""
    message_id: int | None = None
    last_sent_at: float = 0.0
    finalized: bool = False
```

- Key preview state by the originating Telegram reply target:

```python
def _preview_key(self, msg: OutboundMessage) -> str:
    source_message_id = (msg.metadata or {}).get("message_id")
    return f"{msg.chat_id}:{source_message_id or 'root'}"
```

- Add helper methods:
  - `_is_stream_preview_message(...)`
  - `_send_or_edit_preview(...)`
  - `_finalize_preview_with_text(...)`
  - `_clear_preview(...)`
  - `_delete_preview_message(...)`
  - `_render_preview_text(...)`

- Behavior rules:
  - `_telegram_stream` + `_progress` outbounds are delta chunks, not full snapshots; accumulate them in channel state.
  - First visible preview uses `bot.send_message`.
  - Later updates use `bot.edit_message_text`.
  - Respect `streaming_throttle_seconds` and `streaming_min_initial_chars`.
  - Final plain-text reply edits the preview in place when:
    - no media;
    - no PDF-only delivery mode;
    - rendered text fits Telegram edit limits.
  - Otherwise clear the preview and continue with the existing media/text send path.
  - `stream_final` events with empty content should only flush state, not emit a second user-visible message.

**Step 4: Run tests to verify they pass**

Run the command from Step 2.

Expected: PASS

**Step 5: Commit**

```bash
git add backend/nanobot/channels/telegram.py backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py
git commit -m "feat: add telegram preview streaming lifecycle"
```

### Task 4: Make Reply Identity and Finalization Rules Explicit

**Files:**
- Modify: `backend/app/infrastructure/external/channels/nanobot_gateway.py`
- Modify: `backend/nanobot/channels/telegram.py`
- Test: `backend/tests/infrastructure/external/channels/test_nanobot_gateway.py`
- Test: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Step 1: Write the failing tests**

Add tests that prove the original Telegram message ID is preserved all the way into preview/final delivery:

```python
async def test_gateway_preserves_message_id_metadata_for_preview_keying():
    ...

async def test_channel_finalizes_preview_against_original_message_context():
    ...
```

**Step 2: Run test to verify it fails**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_nanobot_gateway.py tests/infrastructure/external/channels/test_telegram_channel_commands.py -q
```

Expected: FAIL if preview logic cannot reliably match the final outbound to its originating inbound message.

**Step 3: Write minimal implementation**

- Ensure `NanobotGateway.send_to_channel()` preserves preview-related metadata unchanged.
- Ensure `TelegramChannel.send()` uses metadata `message_id` consistently for:
  - quote/reply parameters;
  - preview keying;
  - finalization target selection.

**Step 4: Run tests to verify they pass**

Run the command from Step 2.

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/infrastructure/external/channels/nanobot_gateway.py backend/nanobot/channels/telegram.py backend/tests/infrastructure/external/channels/test_nanobot_gateway.py backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py
git commit -m "fix: stabilize telegram preview identity routing"
```

### Task 5: Verification Pass for the First Slice

**Files:**
- Modify only if verification reveals regressions.

**Step 1: Run targeted suite**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/core/test_config_channels.py tests/domain/services/channels/test_message_router.py tests/infrastructure/external/channels/test_nanobot_gateway.py tests/infrastructure/external/channels/test_telegram_channel_commands.py -q
```

Expected: PASS

**Step 2: Run backend quality gates**

```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

Expected: PASS

**Step 3: Commit**

```bash
git add -A
git commit -m "test: verify telegram streaming parity slice"
```

## Phase 2 Enhancement Opportunities from OpenClaw

These are real parity opportunities beyond the first slice. They should be implemented only after Phase 1 is stable.

### Opportunity A: Webhook + Polling Transport Parity

Reference:

- `/home/mac/Desktop/Pythinker-main/openclaw-main/extensions/telegram/src/channel.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/monitor.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/webhook.ts`

Planned Pythinker changes:

- Add Telegram webhook settings to `backend/app/core/config_channels.py` and `backend/nanobot/config/schema.py`.
- Add a webhook startup path to `backend/nanobot/channels/telegram.py`.
- Preserve long polling as the default fallback.

### Opportunity B: Thread and Topic Routing Parity

Reference:

- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/helpers.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-message-context.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/thread-bindings.ts`

Planned Pythinker changes:

- Distinguish DM, regular group, and forum-topic routing.
- Include `message_thread_id` in inbound metadata and outbound send/edit helpers.
- Introduce thread-aware session key overrides in Telegram ingress, not only raw chat IDs.

### Opportunity C: Reply Mode and Edit/Delivery Abstraction Parity

Reference:

- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/send.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot/delivery.ts`

Planned Pythinker changes:

- Replace the single `reply_to_message: bool` toggle with an OpenClaw-style reply mode contract.
- Add dedicated send/edit/delete helpers instead of monolithic logic inside `TelegramChannel.send()`.
- Add HTML-parse fallback and message-not-modified guards on edit retries.

### Opportunity D: Inline Buttons and Callback Routing Parity

Reference:

- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/inline-buttons.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-native-commands.ts`

Planned Pythinker changes:

- Generalize callback routing beyond the current hardcoded PDF action.
- Normalize inline keyboard metadata into a reusable adapter layer.
- Add richer native Telegram command handling and command-menu registration.

### Opportunity E: Telegram Access Policy Parity

Reference:

- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/group-access.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/config/types.telegram.ts`

Planned Pythinker changes:

- Add DM policy modes.
- Add group policy and per-group/per-topic allowlists.
- Add mention-gating rather than today's simple sender allowlist only.

### Opportunity F: Media and Sticker UX Parity

Reference:

- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/sticker-cache.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/voice.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/bot-message-dispatch.sticker-media.test.ts`

Planned Pythinker changes:

- Add sticker-aware media enrichment and sticker resend support.
- Improve voice/media send fallback behavior.
- Preserve richer media metadata through the gateway instead of converting to plain path strings too early.

### Opportunity G: Reasoning-Lane Preview Parity

Reference:

- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/reasoning-lane-coordinator.ts`
- `/home/mac/Desktop/Pythinker-main/openclaw-main/src/telegram/lane-delivery.ts`

Planned Pythinker changes:

- Split answer and reasoning preview streams when the upstream event model can support it cleanly.
- Do not attempt this before the single-lane preview path is stable.

## Execution Notes

- The implementation should preserve current Telegram PDF delivery behavior in `backend/app/domain/services/channels/telegram_delivery_policy.py`.
- `StreamEvent` should be used for preview delivery; empty `ProgressEvent` heartbeats must remain watchdog-only.
- The first slice should not disable Telegram final-only delivery; it should layer preview streaming on top of final-only semantics.
- Use `openclaw-main` behavior as the contract, but adapt to Pythinker’s app gateway boundaries instead of force-fitting OpenClaw’s exact module layout.

## Recommended Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Then pick Phase 2 opportunities in this order: B, C, D, A, E, F, G
