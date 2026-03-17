from stores import auth_store


def seed_users() -> None:
    """Ensure demo user exists and has a token pair."""
    user = auth_store.DEMO_USER
    # Create a stable token pair for the demo user
    if not any(uid == user["id"] for uid in auth_store.access_tokens.values()):
        auth_store.access_tokens["mock_demo_token"] = user["id"]
        auth_store.refresh_tokens["mock_demo_refresh"] = user["id"]
