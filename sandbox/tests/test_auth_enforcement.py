import pytest


class TestSandboxAuthEnforcement:
    def test_production_requires_secret(self):
        from app.core.config import Settings as SandboxSettings

        with pytest.raises(ValueError, match="SANDBOX_API_SECRET.*required"):
            SandboxSettings(SANDBOX_ENVIRONMENT="production", SANDBOX_API_SECRET=None)

    def test_development_allows_missing_secret(self):
        from app.core.config import Settings as SandboxSettings

        settings = SandboxSettings(
            SANDBOX_ENVIRONMENT="development", SANDBOX_API_SECRET=None
        )
        assert settings.SANDBOX_API_SECRET is None

    def test_default_environment_is_development(self):
        from app.core.config import Settings as SandboxSettings

        settings = SandboxSettings()
        assert settings.SANDBOX_ENVIRONMENT == "development"
