# Telegram Inline Button Scope Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add OpenClaw-style Telegram inline button exposure controls so reply markup is only sent where configured, and callback queries are rejected when button scope forbids that surface.

**Architecture:** Reuse the existing Telegram metadata-based `reply_markup` path instead of introducing a new outbound action model. Preserve minimal inbound Telegram chat context (`is_group`) through `MessageRouter` and `TelegramDeliveryPolicy`, then let `TelegramChannel` enforce a new global `inline_buttons_scope` config on outbound keyboards and inbound callbacks.

**Tech Stack:** Python 3.11, python-telegram-bot, pytest, Pydantic v2

---

### Task 1: Lock inline button scope behavior with failing tests

**Files:**
- Modify: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`
- Modify: `backend/tests/domain/services/channels/test_message_router.py`

**Step 1: Write the failing tests**

Add tests for:
- outbound Telegram `reply_markup` is stripped when `inline_buttons_scope="off"`;
- outbound Telegram `reply_markup` is sent in DMs when `inline_buttons_scope="dm"` and stripped in groups;
- outbound Telegram `reply_markup` is sent in groups when `inline_buttons_scope="group"` and stripped in DMs;
- callback queries are ignored when `inline_buttons_scope` forbids the callback chat surface;
- `MessageRouter._telegram_message_id_metadata()` preserves `is_group` for downstream delivery.

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/domain/services/channels/test_message_router.py -k "inline_button or button_scope or preserves_is_group" -q
```

Expected: FAIL because the Telegram config has no inline button scope, reply markup is always sent when present, callbacks only enforce general inbound ACLs, and router metadata does not preserve `is_group`.

### Task 2: Implement config plumbing and Telegram scope enforcement

**Files:**
- Modify: `backend/app/core/config_channels.py`
- Modify: `backend/nanobot/config/schema.py`
- Modify: `backend/app/infrastructure/external/channels/nanobot_gateway.py`
- Modify: `backend/app/interfaces/gateway/gateway_runner.py`
- Modify: `backend/app/domain/services/channels/message_router.py`
- Modify: `backend/app/domain/services/channels/telegram_delivery_policy.py`
- Modify: `backend/nanobot/channels/telegram.py`

**Step 1: Write minimal implementation**

Implement:
- new Telegram config field `inline_buttons_scope` with values `off|dm|group|all|allowlist`;
- gateway wiring from app settings into nanobot Telegram config;
- preservation of `is_group` in Telegram reply metadata;
- Telegram helpers that decide whether inline buttons are allowed for an outbound/callback chat;
- outbound `reply_markup` stripping when the configured scope disallows buttons;
- callback query early-return when the configured scope disallows buttons, while keeping the existing authorization path for allowed surfaces.

**Step 2: Run targeted tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/domain/services/channels/test_message_router.py -k "inline_button or button_scope or preserves_is_group" -q
```

Expected: PASS.

### Task 3: Regression verification

**Files:**
- Verify only

**Step 1: Run broader Telegram verification**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/domain/services/channels/test_message_router.py tests/domain/services/channels/test_telegram_delivery_policy.py tests/core/test_config_channels.py -q
```

Expected: PASS.

**Step 2: Run lint/format on touched files**

Run:

```bash
conda activate pythinker && cd backend && ruff check nanobot/channels/telegram.py nanobot/config/schema.py app/core/config_channels.py app/infrastructure/external/channels/nanobot_gateway.py app/interfaces/gateway/gateway_runner.py app/domain/services/channels/message_router.py app/domain/services/channels/telegram_delivery_policy.py tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/domain/services/channels/test_message_router.py tests/core/test_config_channels.py
```

```bash
conda activate pythinker && cd backend && ruff format --check nanobot/channels/telegram.py nanobot/config/schema.py app/core/config_channels.py app/infrastructure/external/channels/nanobot_gateway.py app/interfaces/gateway/gateway_runner.py app/domain/services/channels/message_router.py app/domain/services/channels/telegram_delivery_policy.py tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/domain/services/channels/test_message_router.py tests/core/test_config_channels.py
```

Expected: PASS.
