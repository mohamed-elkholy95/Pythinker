# Telegram OpenClaw Transport Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild Pythinker's Telegram transport/runtime setup so webhook, polling, dedupe, typing feedback, callback handling, and streaming behavior align with `openclaw-main` as closely as possible within the Python stack.

**Architecture:** Keep `MessageRouter` and `NanobotGateway` as the domain/application boundary, but move Telegram startup and delivery ownership away from PTB's built-in `start_polling`/`start_webhook` transport helpers. Replace them with a Telegram-owned transport layer that registers allowed updates explicitly, runs a custom webhook listener with health and request guards, dedupes updates before dispatch, and supervises polling with restart/backoff semantics.

**Tech Stack:** Python 3.11, `python-telegram-bot`, `aiohttp`, asyncio, pytest, ruff.

---

### Task 1: Lock the webhook transport contract with failing tests

**Files:**
- Modify: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`
- Modify: `backend/nanobot/channels/telegram.py`
- Create: `backend/nanobot/channels/telegram_webhook.py`

**Step 1: Write the failing tests**

Add tests for:
- custom webhook startup path uses our listener helper instead of `updater.start_webhook`
- webhook mode rejects empty secret
- webhook listener exposes `/healthz`
- webhook listener enforces request secret
- webhook listener rejects oversize bodies before Telegram update processing
- webhook shutdown deletes webhook and closes listener

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -k webhook -q
```

Expected: FAIL because `TelegramChannel.start()` still calls PTB's built-in `start_webhook` and no custom listener exists.

**Step 3: Write minimal implementation**

Implement:
- `backend/nanobot/channels/telegram_webhook.py`
  - async listener start/stop helpers
  - `/healthz`
  - body-size limit
  - body-timeout handling
  - secret-token enforcement
  - JSON decode to PTB `Update`
  - dispatch to the running `Application`
- update `backend/nanobot/channels/telegram.py`
  - initialize app once
  - call `bot.set_webhook(...)`
  - use custom listener in webhook mode
  - cleanly `delete_webhook(...)` on shutdown

**Step 4: Run tests to verify they pass**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -k webhook -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/nanobot/channels/telegram.py backend/nanobot/channels/telegram_webhook.py backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py
git commit -m "feat: add custom telegram webhook transport"
```

### Task 2: Lock allowed-updates and handler registration parity

**Files:**
- Modify: `backend/nanobot/channels/telegram.py`
- Modify: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Step 1: Write the failing tests**

Add tests for:
- allowed updates include `message`, `callback_query`, `channel_post`, and `message_reaction`
- callback handler has no restrictive pattern
- channel posts are routed through Telegram inbound handling

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -k "allowed_updates or channel_post or callback_handler" -q
```

Expected: FAIL because current startup still subscribes to only `message` and `callback_query`, and no `channel_post` handler exists.

**Step 3: Write minimal implementation**

Implement:
- explicit `allowed_updates` resolver in `backend/nanobot/channels/telegram.py`
- register channel-post handling using the same inbound normalization path where appropriate
- keep generic callback routing

**Step 4: Run tests to verify they pass**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -k "allowed_updates or channel_post or callback_handler" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/nanobot/channels/telegram.py backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py
git commit -m "feat: expand telegram update coverage"
```

### Task 3: Add polling supervision and restart/backoff behavior

**Files:**
- Modify: `backend/nanobot/channels/telegram.py`
- Modify: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`
- Modify: `backend/tests/infrastructure/external/channels/test_nanobot_gateway.py`

**Step 1: Write the failing tests**

Add tests for:
- polling mode clears webhook before starting
- polling supervisor retries on recoverable startup failure
- stall-restart settings trigger a real restart request instead of only logging

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/infrastructure/external/channels/test_nanobot_gateway.py -k "polling or stall_restart" -q
```

Expected: FAIL because current code starts polling once and watchdog only logs.

**Step 3: Write minimal implementation**

Implement:
- recoverable polling startup wrapper with bounded backoff
- explicit restart path driven by `telegram_polling_stall_restart_enabled`
- connect Telegram channel restart intent to the gateway/channel manager lifecycle in the smallest safe way

**Step 4: Run tests to verify they pass**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/infrastructure/external/channels/test_nanobot_gateway.py -k "polling or stall_restart" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/nanobot/channels/telegram.py backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py backend/tests/infrastructure/external/channels/test_nanobot_gateway.py
git commit -m "feat: supervise telegram polling restarts"
```

### Task 4: Add persisted Telegram update watermarking if a repo-local store is available

**Files:**
- Create: `backend/nanobot/channels/telegram_update_offset_store.py`
- Modify: `backend/nanobot/channels/telegram.py`
- Modify: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Step 1: Write the failing tests**

Add tests for:
- polling resumes from stored update offset
- completed update offset is persisted after processing
- duplicate/replayed update IDs at startup are skipped

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -k "update_offset or replayed update" -q
```

Expected: FAIL because no persisted update watermark exists today.

**Step 3: Write minimal implementation**

Implement:
- small file-backed or existing repo-backed store for Telegram update offsets
- load/store hooks inside the polling loop
- only persist watermarks after safe processing completion

**Step 4: Run tests to verify they pass**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -k "update_offset or replayed update" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/nanobot/channels/telegram.py backend/nanobot/channels/telegram_update_offset_store.py backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py
git commit -m "feat: persist telegram update offsets"
```

### Task 5: Keep Telegram typing feedback active through long-running backend work

**Files:**
- Modify: `backend/app/domain/services/channels/message_router.py`
- Modify: `backend/nanobot/channels/telegram.py`
- Modify: `backend/tests/domain/services/channels/test_message_router.py`
- Modify: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`

**Step 1: Write the failing test**

Add tests for:
- research ACKs mark keep-typing metadata
- progress/stream preview sends do not stop typing
- final user-facing completion stops typing

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/channels/test_message_router.py tests/infrastructure/external/channels/test_telegram_channel_commands.py -k typing -q
```

Expected: FAIL if typing still stops on the first outbound.

**Step 3: Write minimal implementation**

Implement:
- router metadata flag for keep-typing ACK/progress states
- Telegram send-path logic that preserves typing across progress/work states and stops on final completion

**Step 4: Run tests to verify they pass**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/channels/test_message_router.py tests/infrastructure/external/channels/test_telegram_channel_commands.py -k typing -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/domain/services/channels/message_router.py backend/nanobot/channels/telegram.py backend/tests/domain/services/channels/test_message_router.py backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py
git commit -m "feat: keep telegram typing active during long-running work"
```

### Task 6: Final verification

**Files:**
- Modify: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`
- Modify: `backend/tests/infrastructure/external/channels/test_nanobot_gateway.py`
- Modify: `backend/tests/domain/services/channels/test_message_router.py`

**Step 1: Run focused verification**

Run:

```bash
conda activate pythinker && cd backend && ruff check app/domain/services/channels/message_router.py app/infrastructure/external/channels/nanobot_gateway.py app/interfaces/gateway/gateway_runner.py nanobot/channels/telegram.py nanobot/channels/telegram_webhook.py nanobot/channels/telegram_update_offset_store.py tests/domain/services/channels/test_message_router.py tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/infrastructure/external/channels/test_nanobot_gateway.py
conda activate pythinker && cd backend && ruff format --check app/domain/services/channels/message_router.py app/infrastructure/external/channels/nanobot_gateway.py app/interfaces/gateway/gateway_runner.py nanobot/channels/telegram.py nanobot/channels/telegram_webhook.py nanobot/channels/telegram_update_offset_store.py tests/domain/services/channels/test_message_router.py tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/infrastructure/external/channels/test_nanobot_gateway.py
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/channels/test_message_router.py tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/infrastructure/external/channels/test_nanobot_gateway.py -q
```

Expected: all green.

**Step 2: Run broader backend verification if transport changes touched shared startup paths**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/interfaces/gateway -q
```

Expected: PASS or explicit localized failures to fix.

**Step 3: Commit**

```bash
git add backend/app/domain/services/channels/message_router.py backend/app/infrastructure/external/channels/nanobot_gateway.py backend/app/interfaces/gateway/gateway_runner.py backend/nanobot/channels/telegram.py backend/nanobot/channels/telegram_webhook.py backend/nanobot/channels/telegram_update_offset_store.py backend/tests/domain/services/channels/test_message_router.py backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py backend/tests/infrastructure/external/channels/test_nanobot_gateway.py docs/plans/2026-03-08-telegram-openclaw-transport-parity-implementation.md
git commit -m "feat: align telegram transport with openclaw"
```
