"""Tests for OpenRouter detection, structured output support, and instructor adapter."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.infrastructure.external.llm.instructor_adapter import (
    INSTRUCTOR_AVAILABLE,
    select_instructor_mode,
)
from app.infrastructure.external.llm.openai_llm import OpenAILLM

# ── helpers ──────────────────────────────────────────────────────────────


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content

    def model_dump(self) -> dict[str, str]:
        return {"role": "assistant", "content": self.content}


class _FakeChoice:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = None

    def model_dump(self) -> dict[str, str]:
        return {"ok": "true"}


class _SampleModel(BaseModel):
    name: str
    value: int


def _build_llm(
    *,
    api_base: str = "https://provider.example/v1",
    model_name: str = "gpt-4o-mini",
) -> OpenAILLM:
    """Build an OpenAILLM instance bypassing __init__ for unit testing."""
    llm = OpenAILLM.__new__(OpenAILLM)
    llm._is_thinking_api = False
    llm._is_mlx_mode = False
    llm._is_glm_api = False
    llm._is_openrouter = "openrouter" in api_base.lower()
    llm._model_name = model_name
    llm._temperature = 0.0
    llm._max_tokens = 256
    llm._api_base = api_base
    llm._supports_stream_usage = False
    llm._cache_manager = None
    llm._last_stream_metadata = None
    llm._record_usage = AsyncMock()
    llm._record_stream_usage = AsyncMock()
    llm._record_usage_counts = AsyncMock()
    return llm


# ── OpenRouter detection ─────────────────────────────────────────────────


class TestDetectOpenRouter:
    def test_openrouter_api_base(self) -> None:
        llm = _build_llm(api_base="https://openrouter.ai/api/v1")
        assert llm._detect_openrouter() is True

    def test_openrouter_case_insensitive(self) -> None:
        llm = _build_llm(api_base="https://OpenRouter.AI/api/v1")
        assert llm._detect_openrouter() is True

    def test_non_openrouter(self) -> None:
        llm = _build_llm(api_base="https://api.openai.com/v1")
        assert llm._detect_openrouter() is False

    def test_empty_api_base(self) -> None:
        llm = _build_llm(api_base="")
        llm._api_base = ""
        assert llm._detect_openrouter() is False

    def test_none_api_base(self) -> None:
        llm = _build_llm()
        llm._api_base = None
        assert llm._detect_openrouter() is False

    def test_is_openrouter_flag_set_in_build(self) -> None:
        llm = _build_llm(api_base="https://openrouter.ai/api/v1")
        assert llm._is_openrouter is True

    def test_is_openrouter_flag_not_set(self) -> None:
        llm = _build_llm(api_base="https://api.openai.com/v1")
        assert llm._is_openrouter is False


# ── _supports_structured_output ──────────────────────────────────────────


class TestSupportsStructuredOutput:
    def test_openrouter_returns_true(self) -> None:
        llm = _build_llm(
            api_base="https://openrouter.ai/api/v1",
            model_name="qwen/qwen3-coder-next",
        )
        assert llm._supports_structured_output() is True

    def test_gpt4o_returns_true(self) -> None:
        llm = _build_llm(
            api_base="https://api.openai.com/v1",
            model_name="gpt-4o",
        )
        assert llm._supports_structured_output() is True

    def test_gpt5_returns_true(self) -> None:
        llm = _build_llm(
            api_base="https://api.openai.com/v1",
            model_name="gpt-5-mini",
        )
        assert llm._supports_structured_output() is True

    def test_mlx_returns_false(self) -> None:
        llm = _build_llm(
            api_base="http://localhost:8081/v1",
            model_name="mlx-community/some-model",
        )
        llm._is_mlx_mode = True
        assert llm._supports_structured_output() is False

    def test_unknown_provider_returns_false(self) -> None:
        llm = _build_llm(
            api_base="https://custom-llm.example.com/v1",
            model_name="custom-model",
        )
        assert llm._supports_structured_output() is False


# ── _supports_json_object_format ─────────────────────────────────────────


class TestSupportsJsonObjectFormat:
    def test_openrouter_returns_true(self) -> None:
        llm = _build_llm(
            api_base="https://openrouter.ai/api/v1",
            model_name="qwen/qwen3-coder-next",
        )
        assert llm._supports_json_object_format() is True

    def test_openai_returns_true(self) -> None:
        llm = _build_llm(
            api_base="https://api.openai.com/v1",
            model_name="gpt-4o",
        )
        assert llm._supports_json_object_format() is True

    def test_glm_returns_false(self) -> None:
        llm = _build_llm(
            api_base="https://api.z.ai/api/paas/v4",
            model_name="glm-5",
        )
        llm._is_glm_api = True
        assert llm._supports_json_object_format() is False

    def test_unknown_provider_returns_false(self) -> None:
        llm = _build_llm(
            api_base="https://custom-llm.example.com/v1",
            model_name="custom-model",
        )
        assert llm._supports_json_object_format() is False


# ── instructor adapter ───────────────────────────────────────────────────


@pytest.mark.skipif(not INSTRUCTOR_AVAILABLE, reason="instructor not installed")
class TestSelectInstructorMode:
    def test_json_schema_mode(self) -> None:
        import instructor

        mode = select_instructor_mode(supports_json_schema=True, supports_json_object=True)
        assert mode == instructor.Mode.JSON_SCHEMA

    def test_json_mode(self) -> None:
        import instructor

        mode = select_instructor_mode(supports_json_schema=False, supports_json_object=True)
        assert mode == instructor.Mode.JSON

    def test_md_json_fallback(self) -> None:
        import instructor

        mode = select_instructor_mode(supports_json_schema=False, supports_json_object=False)
        assert mode == instructor.Mode.MD_JSON

    def test_json_schema_preferred_over_json(self) -> None:
        import instructor

        mode = select_instructor_mode(supports_json_schema=True, supports_json_object=False)
        assert mode == instructor.Mode.JSON_SCHEMA

    def test_openrouter_uses_dedicated_mode(self) -> None:
        import instructor

        mode = select_instructor_mode(
            supports_json_schema=True, supports_json_object=True, is_openrouter=True
        )
        assert mode == instructor.Mode.OPENROUTER_STRUCTURED_OUTPUTS

    def test_openrouter_overrides_json_schema(self) -> None:
        """OpenRouter mode takes precedence even when json_schema is supported."""
        import instructor

        mode = select_instructor_mode(
            supports_json_schema=False, supports_json_object=False, is_openrouter=True
        )
        assert mode == instructor.Mode.OPENROUTER_STRUCTURED_OUTPUTS


# ── ask_structured with OpenRouter uses json_schema ──────────────────────


class TestAskStructuredOpenRouter:
    @pytest.mark.asyncio
    async def test_openrouter_uses_json_schema_format(self) -> None:
        """Verify that OpenRouter gets native json_schema response_format."""
        llm = _build_llm(
            api_base="https://openrouter.ai/api/v1",
            model_name="qwen/qwen3-coder-next",
        )

        response_json = '{"name": "test", "value": 42}'
        create_mock = AsyncMock(return_value=_FakeResponse(response_json))
        llm.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        # Disable instructor to test the manual path's response_format
        with patch(
            "app.infrastructure.external.llm.openai_llm.get_settings"
        ) as mock_settings:
            settings_obj = SimpleNamespace(
                use_instructor_structured_output=False,
            )
            mock_settings.return_value = settings_obj

            result = await llm.ask_structured(
                messages=[{"role": "user", "content": "test"}],
                response_model=_SampleModel,
                enable_caching=False,
            )

        assert result.name == "test"
        assert result.value == 42

        # Verify the response_format parameter sent to the API
        call_kwargs = create_mock.call_args.kwargs
        assert call_kwargs["response_format"]["type"] == "json_schema"
        assert call_kwargs["response_format"]["json_schema"]["name"] == "_SampleModel"
        assert call_kwargs["response_format"]["json_schema"]["strict"] is True

    @pytest.mark.asyncio
    async def test_openrouter_includes_require_parameters(self) -> None:
        """Verify that OpenRouter requests include provider.require_parameters."""
        llm = _build_llm(
            api_base="https://openrouter.ai/api/v1",
            model_name="qwen/qwen3-coder-next",
        )

        response_json = '{"name": "test", "value": 42}'
        create_mock = AsyncMock(return_value=_FakeResponse(response_json))
        llm.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        with patch(
            "app.infrastructure.external.llm.openai_llm.get_settings"
        ) as mock_settings:
            settings_obj = SimpleNamespace(
                use_instructor_structured_output=False,
            )
            mock_settings.return_value = settings_obj

            await llm.ask_structured(
                messages=[{"role": "user", "content": "test"}],
                response_model=_SampleModel,
                enable_caching=False,
            )

        call_kwargs = create_mock.call_args.kwargs
        extra_body = call_kwargs.get("extra_body", {})
        assert extra_body.get("provider", {}).get("require_parameters") is True

    @pytest.mark.asyncio
    @pytest.mark.skipif(not INSTRUCTOR_AVAILABLE, reason="instructor not installed")
    async def test_openrouter_with_instructor(self) -> None:
        """Verify instructor path is used when available and enabled."""
        llm = _build_llm(
            api_base="https://openrouter.ai/api/v1",
            model_name="qwen/qwen3-coder-next",
        )

        expected_result = _SampleModel(name="instructor", value=99)

        # Mock the patched client's create_with_completion
        mock_completion = _FakeResponse('{"name": "instructor", "value": 99}')
        mock_create = AsyncMock(return_value=(expected_result, mock_completion))

        llm.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock()))
        )

        with (
            patch(
                "app.infrastructure.external.llm.openai_llm.get_settings"
            ) as mock_settings,
            patch(
                "app.infrastructure.external.llm.instructor_adapter.instructor"
            ) as mock_instructor,
        ):
            settings_obj = SimpleNamespace(
                use_instructor_structured_output=True,
            )
            mock_settings.return_value = settings_obj

            # Mock instructor.from_openai to return a patched client
            mock_patched = SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create_with_completion=mock_create)
                )
            )
            mock_instructor.from_openai.return_value = mock_patched
            mock_instructor.Mode.JSON_SCHEMA = "json_schema"
            mock_instructor.Mode.JSON = "json"
            mock_instructor.Mode.MD_JSON = "md_json"

            result = await llm.ask_structured(
                messages=[{"role": "user", "content": "test"}],
                response_model=_SampleModel,
                enable_caching=False,
            )

        assert result.name == "instructor"
        assert result.value == 99
        # Verify raw completion was passed for usage recording
        llm._record_usage.assert_awaited_once_with(mock_completion)


class TestAskOpenRouterProvider:
    @pytest.mark.asyncio
    async def test_ask_openrouter_with_response_format_adds_provider_hint(self) -> None:
        """Verify ask() adds require_parameters when response_format is set on OpenRouter."""
        llm = _build_llm(
            api_base="https://openrouter.ai/api/v1",
            model_name="qwen/qwen3-coder-next",
        )

        create_mock = AsyncMock(return_value=_FakeResponse("hello"))
        llm.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        await llm.ask(
            messages=[{"role": "user", "content": "test"}],
            response_format={"type": "json_object"},
            enable_caching=False,
        )

        call_kwargs = create_mock.call_args.kwargs
        extra_body = call_kwargs.get("extra_body", {})
        assert extra_body.get("provider", {}).get("require_parameters") is True

    @pytest.mark.asyncio
    async def test_ask_openrouter_without_response_format_no_hint(self) -> None:
        """Verify ask() does NOT add require_parameters when no response_format."""
        llm = _build_llm(
            api_base="https://openrouter.ai/api/v1",
            model_name="qwen/qwen3-coder-next",
        )

        create_mock = AsyncMock(return_value=_FakeResponse("hello"))
        llm.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        await llm.ask(
            messages=[{"role": "user", "content": "test"}],
            enable_caching=False,
        )

        call_kwargs = create_mock.call_args.kwargs
        extra_body = call_kwargs.get("extra_body", {})
        # No response_format → no require_parameters needed
        assert "provider" not in extra_body
