# Telegram Account Linking — Design

**Goal:** Allow web UI users to link their Telegram account so that Telegram bot sessions appear in the web UI under the same user identity.

**Architecture:** Code-based linking via Redis-backed temporary codes. Web UI generates a 6-digit code; user sends `/link CODE` to @Pythinkbot; system updates `user_channel_links` to map the Telegram identity to the web user_id.

**Scope:** Telegram only. Architecture naturally extends to Discord/Slack via the existing `ChannelType` enum.

---

## Linking Flow

```
Web UI (AccountSettings)          Telegram Bot (@Pythinkbot)
       │                                │
  [Link Telegram] button                │
       │                                │
       ▼                                │
  POST /api/v1/user/channel-link        │
       │                                │
       ▼                                │
  Redis: link:{CODE} → user_id          │
  (15 min TTL, single-use)              │
       │                         User sends: /link CODE
       │                                │
       │                                ▼
       │                      MessageRouter /link handler
       │                                │
       │                                ▼
       │                      Redis: validate & consume code
       │                                │
       │                                ▼
       └────────────────────── MongoDB: user_channel_links
                               set user_id = web_user_id
                                        │
                                        ▼
                               Future sessions use web user_id
                               → visible in web UI session list
```

## After Linking

When a linked Telegram user sends a message:

1. `MessageRouter._resolve_user()` calls `get_user_by_channel(TELEGRAM, sender_id)`
2. Returns the **web user_id** (e.g., `aBcDeFgHiJkLmNoPqRsT`)
3. Session is created under web user_id
4. Web UI's session list shows it (same user_id as authenticated web user)

## Backend Components

### New API Endpoints (3)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/user/channel-link` | Required | Generate 6-digit link code, store in Redis (15 min TTL) |
| `GET` | `/api/v1/user/channel-links` | Required | List linked channels for current user |
| `DELETE` | `/api/v1/user/channel-link/{channel}` | Required | Unlink a channel |

### New Slash Command

Add `/link` to `MessageRouter.SLASH_COMMANDS`:

- `/link CODE` — Validates code in Redis, updates `user_channel_links`, migrates `channel_sessions`
- Invalid/expired code → error message
- Already linked → informational message

### Repository Updates (`MongoUserChannelRepository`)

New methods:

- `link_channel_to_user(channel, sender_id, web_user_id)` — Upsert `user_channel_links` doc with web user_id
- `get_linked_channels(user_id)` — Returns list of linked channels for a user
- `unlink_channel(user_id, channel)` — Removes channel link document
- `migrate_sessions(old_user_id, new_user_id, channel)` — Updates `channel_sessions` docs from old to new user_id

## Frontend Components

### AccountSettings.vue Update

Add "Linked Channels" section below the existing profile card:

- **Unlinked state:** "Link Telegram" button
- **Code generated state:** Shows 6-digit code + copy button + instructions ("Send `/link CODE` to @Pythinkbot") + countdown timer
- **Linked state:** Shows Telegram username/ID + "Unlink" button

### New API Functions (`frontend/src/api/`)

- `generateChannelLinkCode(channel)` → `{code, expires_at}`
- `getLinkedChannels()` → `[{channel, sender_id, linked_at}]`
- `unlinkChannel(channel)` → success

## Data Model

### Redis — Link Code (temporary)

```
Key:    channel_link:{CODE}
Value:  JSON {user_id, channel, created_at}
TTL:    900 seconds (15 minutes)
```

### MongoDB — `user_channel_links` (existing collection, no schema change)

```json
{
  "user_id": "aBcDeFgHiJkLmNoPqRsT",  // web user_id (was channel-{hex})
  "channel": "telegram",
  "sender_id": "5829880422|UNIDM9",
  "chat_id": "5829880422",
  "created_at": "2026-03-02T...",
  "linked_at": "2026-03-02T..."         // NEW: timestamp of linking
}
```

## Error Handling

| Scenario | Response |
|----------|----------|
| Invalid/expired code | "Invalid or expired link code. Generate a new one from the web UI." |
| Already linked to same user | "This Telegram account is already linked to your account." |
| Already linked to different user | "This Telegram account is linked to another account. Unlink it first." |
| Code already used | Same as expired (Redis key deleted after use) |
| Unlink while session active | Session continues (user_id doesn't change mid-session) |

## Security

- 6 alphanumeric characters: ~2.1 billion combinations
- 15-minute TTL — codes auto-expire
- Single-use — deleted from Redis after successful validation
- Rate limit: max 5 code generations per user per hour (Redis counter)
- Only authenticated web users can generate codes
- `/link` only works in private chat (not group chats)
