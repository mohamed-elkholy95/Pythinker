"""Tests for the DiscussFlow service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import get_settings
from app.domain.models.message import Message
from app.domain.services.flows.discuss import DiscussFlow
from app.domain.services.prompts.discuss import build_discuss_prompt


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


class TestBuildDiscussPrompt:
    """Tests for build_discuss_prompt function."""

    def test_build_discuss_prompt_includes_language(self) -> None:
        """build_discuss_prompt should include the language parameter in the output."""
        prompt = build_discuss_prompt(
            message="Hello",
            attachments="",
            language="Chinese",
        )
        assert "Language: Chinese" in prompt

    def test_build_discuss_prompt_default_language(self) -> None:
        """build_discuss_prompt should default to English if not specified."""
        prompt = build_discuss_prompt(message="Hello")
        assert "Language: English" in prompt

    def test_build_discuss_prompt_custom_language(self) -> None:
        """build_discuss_prompt should use the provided language."""
        for lang in ["Japanese", "Spanish", "French", "German"]:
            prompt = build_discuss_prompt(message="Hello", language=lang)
            assert f"Language: {lang}" in prompt


class TestDiscussFlowLanguageIntegration:
    """Integration tests for language configuration in DiscussFlow."""

    @pytest.mark.asyncio
    async def test_discuss_flow_uses_configured_language(self) -> None:
        """DiscussFlow should use the configured language from settings in prompts."""
        # Create mock settings with custom language
        mock_settings = MagicMock()
        mock_settings.default_language = "Chinese"

        # Create minimal mocks for DiscussFlow dependencies
        mock_agent_repo = MagicMock()
        mock_session_repo = MagicMock()
        mock_llm = MagicMock()
        mock_json_parser = MagicMock()

        # Patch get_settings in the discuss module
        with patch(
            "app.domain.services.flows.discuss.get_settings",
            return_value=mock_settings,
        ):
            # Create DiscussFlow instance
            flow = DiscussFlow(
                agent_id="test-agent",
                agent_repository=mock_agent_repo,
                session_id="test-session",
                session_repository=mock_session_repo,
                llm=mock_llm,
                json_parser=mock_json_parser,
            )

            # Patch build_discuss_prompt to capture what it's called with
            with patch(
                "app.domain.services.flows.discuss.build_discuss_prompt",
                wraps=build_discuss_prompt,
            ) as mock_build_prompt:
                # Mock the agent.execute to return an async generator
                async def mock_execute(prompt: str):
                    # Return empty generator - we just care about what prompt was used
                    return
                    yield  # Makes this an async generator

                flow._agent.execute = mock_execute

                # Create test message
                test_message = Message(message="Hello, world!")

                # Run the flow (consume the generator)
                async for _ in flow.run(test_message):
                    pass

                # Verify build_discuss_prompt was called with the configured language
                mock_build_prompt.assert_called_once()
                call_kwargs = mock_build_prompt.call_args
                assert call_kwargs.kwargs.get("language") == "Chinese"

    @pytest.mark.asyncio
    async def test_discuss_flow_prompt_contains_configured_language(self) -> None:
        """The actual prompt passed to the agent should contain the configured language."""
        mock_settings = MagicMock()
        mock_settings.default_language = "Japanese"

        mock_agent_repo = MagicMock()
        mock_session_repo = MagicMock()
        mock_llm = MagicMock()
        mock_json_parser = MagicMock()

        captured_prompt: str | None = None

        with patch(
            "app.domain.services.flows.discuss.get_settings",
            return_value=mock_settings,
        ):
            flow = DiscussFlow(
                agent_id="test-agent",
                agent_repository=mock_agent_repo,
                session_id="test-session",
                session_repository=mock_session_repo,
                llm=mock_llm,
                json_parser=mock_json_parser,
            )

            # Mock agent.execute to capture the prompt
            async def mock_execute(prompt: str):
                nonlocal captured_prompt
                captured_prompt = prompt
                return
                yield

            flow._agent.execute = mock_execute

            test_message = Message(message="What is the weather?")

            async for _ in flow.run(test_message):
                pass

            # Verify the prompt contains the configured language
            assert captured_prompt is not None
            assert "Language: Japanese" in captured_prompt
            assert "What is the weather?" in captured_prompt
