from app.core.config import Settings


def test_sandbox_lifecycle_mode_defaults_to_static() -> None:
    settings = Settings.model_construct()
    assert settings.sandbox_lifecycle_mode == "static"


def test_static_address_flag_disabled_for_ephemeral_mode() -> None:
    settings = Settings.model_construct(
        sandbox_lifecycle_mode="ephemeral",
        sandbox_address="sandbox,sandbox2",
    )
    assert settings.uses_static_sandbox_addresses is False


def test_static_address_flag_enabled_for_static_mode() -> None:
    settings = Settings.model_construct(
        sandbox_lifecycle_mode="static",
        sandbox_address="sandbox,sandbox2",
    )
    assert settings.uses_static_sandbox_addresses is True
