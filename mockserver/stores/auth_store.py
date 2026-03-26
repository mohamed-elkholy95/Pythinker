from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone

DEMO_USER = {
    "id": "usr_demo_001",
    "fullname": "Demo User",
    "email": "demo@pythinker.ai",
    "role": "admin",
    "is_active": True,
    "email_verified": True,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
    "last_login_at": None,
}

# user_id -> user dict
users: dict[str, dict] = {DEMO_USER["id"]: {**DEMO_USER}}

# token -> user_id
access_tokens: dict[str, str] = {}
refresh_tokens: dict[str, str] = {}
verification_states: dict[str, dict] = {}

VERIFICATION_EXPIRY_SECONDS = 600
VERIFICATION_RESEND_COOLDOWN_SECONDS = 60
VERIFICATION_MAX_RESENDS = 3


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


def build_verification_state() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "expires_at": (
            now + timedelta(seconds=VERIFICATION_EXPIRY_SECONDS)
        ).isoformat(),
        "resend_available_at": (
            now + timedelta(seconds=VERIFICATION_RESEND_COOLDOWN_SECONDS)
        ).isoformat(),
        "resends_remaining": VERIFICATION_MAX_RESENDS,
    }


def issue_verification_state(email: str) -> dict:
    state = build_verification_state()
    verification_states[email.lower()] = state
    return state


def get_verification_state(email: str) -> dict:
    return verification_states.get(email.lower()) or issue_verification_state(email)


def verify_email(email: str) -> dict | None:
    user = get_user_by_email(email)
    if not user:
        return None
    user["email_verified"] = True
    verification_states.pop(email.lower(), None)
    return user


def register_user(fullname: str, email: str) -> dict:
    uid = f"usr_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    user = {
        "id": uid,
        "fullname": fullname,
        "email": email.lower(),
        "role": "user",
        "is_active": True,
        "email_verified": False,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    users[uid] = user
    return user
