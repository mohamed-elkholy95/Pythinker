# Telegram Command/Callback Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Telegram channel honor app-registered custom slash commands, expose them in Telegram help/menu surfaces, and enforce channel policy for callback interactions.

**Architecture:** Reuse the existing app-layer `CommandRegistry` instead of inventing a Telegram-only command abstraction. Keep built-in Telegram command handlers for `/start` and `/help`, but let unknown slash commands consult the registry so custom commands and aliases are forwarded into the existing message bus path. Apply the same inbound authorization logic to callback queries before forwarding synthetic messages.

**Tech Stack:** Python 3.11, python-telegram-bot, pytest, Pydantic v2

---

### Task 1: Lock Telegram custom command behavior with failing tests

**Files:**
- Modify: `backend/tests/infrastructure/external/channels/test_telegram_channel_commands.py`
- Test support: `backend/tests/domain/services/test_command_registry.py`

**Step 1: Write the failing tests**

Add tests for:
- Telegram `set_my_commands()` includes app-registered primary custom commands.
- `/help` output includes app-registered primary custom commands.
- Unknown slash commands that exist in the registry are forwarded to `_handle_message` instead of replying with the generic unknown-command hint.
- Callback queries respect the same inbound authorization rules as messages.

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -k "custom_command or callback_query_authorization" -q
```

Expected: FAIL because Telegram currently only knows its hard-coded commands and callback queries bypass `_is_inbound_allowed()`.

### Task 2: Implement Telegram command-registry/menu integration and callback ACLs

**Files:**
- Modify: `backend/nanobot/channels/telegram.py`

**Step 1: Write minimal implementation**

Implement:
- helper to collect built-in Telegram commands plus primary commands from `CommandRegistry`
- menu registration via `set_my_commands()` using that merged list, capped to Telegram’s command menu limit
- dynamic help-text builder that appends primary custom commands
- registry-aware command recognition in `_unknown_command()` so registered commands/aliases forward via `_forward_command()`
- callback authorization check in `_on_callback_query()` using the same `_is_inbound_allowed()` path as message handling

**Step 2: Run targeted tests**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py -k "custom_command or callback_query_authorization" -q
```

Expected: PASS.

### Task 3: Regression verification

**Files:**
- Verify only

**Step 1: Run broader Telegram verification**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/external/channels/test_telegram_channel_commands.py tests/domain/services/test_command_registry.py tests/domain/services/channels/test_message_router.py -q
```

Expected: PASS.
