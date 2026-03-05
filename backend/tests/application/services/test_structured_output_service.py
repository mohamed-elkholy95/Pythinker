from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from app.application.services.structured_output_service import StructuredOutputService
from app.domain.models.structured_output import (
    ErrorCategory,
    OutputTier,
    StopReason,
    StructuredOutputRequest,
    StructuredOutputStrategy,
    StructuredRefusalError,
)


class _SimpleModel(BaseModel):
    value: int


class _StrictLLM:
    model_name = "gpt-4o"

    async def ask_structured(self, *args: Any, **kwargs: Any) -> _SimpleModel:
        return _SimpleModel(value=7)

    async def ask(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"content": '{"value": 7}'}


class _RefusingLLM(_StrictLLM):
    async def ask_structured(self, *args: Any, **kwargs: Any) -> _SimpleModel:
        raise StructuredRefusalError("Model refused")


class _LenientOnlyLLM:
    model_name = "llama3.2"

    async def ask_structured(self, *args: Any, **kwargs: Any) -> _SimpleModel:
        raise ValueError("strict path unavailable")

    async def ask(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"content": '{"value": 3}'}


@pytest.mark.asyncio
async def test_structured_output_service_tier_a_success() -> None:
    service = StructuredOutputService(llm=_StrictLLM())
    request = StructuredOutputRequest(
        request_id="req-a-1",
        schema_model=_SimpleModel,
        tier=OutputTier.A,
        messages=[{"role": "user", "content": "Return value"}],
    )

    result = await service.execute(request)

    assert result.stop_reason == StopReason.SUCCESS
    assert result.parsed is not None
    assert result.parsed.value == 7
    assert result.strategy_used in {
        StructuredOutputStrategy.OPENAI_STRICT_JSON_SCHEMA,
        StructuredOutputStrategy.INSTRUCTOR_TOOLS_STRICT,
        StructuredOutputStrategy.ANTHROPIC_OUTPUT_CONFIG,
    }


@pytest.mark.asyncio
async def test_structured_output_service_maps_refusal_to_typed_outcome() -> None:
    service = StructuredOutputService(llm=_RefusingLLM())
    request = StructuredOutputRequest(
        request_id="req-a-2",
        schema_model=_SimpleModel,
        tier=OutputTier.A,
        messages=[{"role": "user", "content": "Refuse"}],
    )

    result = await service.execute(request)

    assert result.stop_reason == StopReason.REFUSAL
    assert result.error_type == ErrorCategory.SAFETY
    assert result.parsed is None


@pytest.mark.asyncio
async def test_structured_output_service_uses_model_validate_json_for_lenient_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StructuredOutputService(llm=_LenientOnlyLLM())
    request = StructuredOutputRequest(
        request_id="req-b-1",
        schema_model=_SimpleModel,
        tier=OutputTier.B,
        messages=[{"role": "user", "content": "Return JSON"}],
    )

    called = {"value": False}
    original = _SimpleModel.model_validate_json

    @classmethod
    def _spy(cls, json_data: str, *args: Any, **kwargs: Any) -> _SimpleModel:
        called["value"] = True
        return original(json_data, *args, **kwargs)

    monkeypatch.setattr(_SimpleModel, "model_validate_json", _spy)

    result = await service.execute(request)

    assert called["value"] is True
    assert result.stop_reason == StopReason.SUCCESS
    assert result.parsed is not None
    assert result.parsed.value == 3
