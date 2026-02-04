"""Tests for the DiscussFlow service."""

from app.core.config import get_settings


class TestDiscussFlowLanguageConfig:
    """Tests for language configuration in discuss flow."""

    def test_settings_has_default_language_attribute(self) -> None:
        """Settings should have a default_language attribute."""
        settings = get_settings()
        assert hasattr(settings, "default_language")

    def test_default_language_is_english(self) -> None:
        """Default language should be English."""
        settings = get_settings()
        assert settings.default_language == "English"

    def test_default_language_is_string(self) -> None:
        """Default language should be a string type."""
        settings = get_settings()
        assert isinstance(settings.default_language, str)
