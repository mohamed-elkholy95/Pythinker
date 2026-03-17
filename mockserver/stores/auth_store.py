from __future__ import annotations
import uuid
from datetime import datetime, timezone

DEMO_USER = {
    "id": "usr_demo_001",
    "fullname": "Demo User",
    "email": "demo@pythinker.ai",
    "role": "admin",
    "is_active": True,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
    "last_login_at": None,
}

# user_id -> user dict
users: dict[str, dict] = {DEMO_USER["id"]: {**DEMO_USER}}

# token -> user_id
access_tokens: dict[str, str] = {}
refresh_tokens: dict[str, str] = {}


def create_token_pair(user_id: str) -> tuple[str, str]:
    access = f"mock_access_{uuid.uuid4().hex[:16]}"
    refresh = f"mock_refresh_{uuid.uuid4().hex[:16]}"
    access_tokens[access] = user_id
    refresh_tokens[refresh] = user_id
    return access, refresh


def get_user_by_token(token: str) -> dict | None:
    uid = access_tokens.get(token)
    if uid:
        return users.get(uid)
    return None


def get_user_by_email(email: str) -> dict | None:
    for u in users.values():
        if u["email"] == email.lower():
            return u
    return None


def get_user_by_id(user_id: str) -> dict | None:
    return users.get(user_id)


def register_user(fullname: str, email: str) -> dict:
    uid = f"usr_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    user = {
        "id": uid,
        "fullname": fullname,
        "email": email.lower(),
        "role": "user",
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    users[uid] = user
    return user
