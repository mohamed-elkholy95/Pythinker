from __future__ import annotations

import logging
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.domain.external.llm_capabilities import ProviderCapabilities, get_capabilities
from app.domain.models.structured_output import (
    ErrorCategory,
    OutputTier,
    StopReason,
    StructuredContentFilterError,
    StructuredOutputError,
    StructuredOutputRequest,
    StructuredOutputResult,
    StructuredOutputStrategy,
    StructuredOutputUnsupportedError,
    StructuredRefusalError,
    StructuredSchemaValidationError,
    StructuredTruncationError,
)
from app.domain.services.validation.schema_profile import SchemaComplexityProfile
from app.domain.utils.json_repair import extract_json_text

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _metric_inc(metric_name: str, labels: dict[str, str]) -> None:
    try:
        from app.core import prometheus_metrics as pm

        metric = getattr(pm, metric_name, None)
        if metric is not None:
            metric.inc(labels)
    except Exception:
        logger.debug("Structured output metric emission failed (%s)", metric_name, exc_info=True)


class StructuredOutputService:
    """Tier-aware structured output orchestrator.

    Centralizes strategy selection, validation, retries, and typed outcome
    mapping for all structured LLM responses.
    """

    def __init__(self, llm: Any):
        self._llm = llm

    async def execute(self, request: StructuredOutputRequest[T]) -> StructuredOutputResult[T]:
        start = time.monotonic()
        attempts = 0
        model_name = str(getattr(self._llm, "model_name", "") or "")
        api_base = getattr(self._llm, "_api_base", None) or getattr(self._llm, "api_base", None)
        caps = get_capabilities(model_name, api_base)
        profile = request.complexity_profile or SchemaComplexityProfile.from_model(request.schema_model)
        strategies = self._candidate_strategies(
            tier=request.tier,
            model_name=model_name,
            capabilities=caps,
            profile=profile,
        )

        if not strategies:
            strategies = [StructuredOutputStrategy.UNSUPPORTED]

        _metric_inc(
            "structured_output_requests_total",
            {"tier": request.tier.value, "strategy": strategies[0].value},
        )

        if strategies[0] == StructuredOutputStrategy.UNSUPPORTED:
            return self._result(
                request=request,
                start=start,
                attempts=1,
                strategy=StructuredOutputStrategy.UNSUPPORTED,
                stop_reason=StopReason.UNSUPPORTED,
                error_type=ErrorCategory.UNSUPPORTED,
            )

        for idx, strategy in enumerate(strategies):
            if idx > 0:
                _metric_inc(
                    "structured_output_fallback_total",
                    {"tier": request.tier.value, "strategy": strategy.value},
                )

            messages = list(request.messages)

            for transport_attempt in range(request.max_transport_retries + 1):
                for schema_attempt in range(request.max_schema_retries + 1):
                    attempts += 1
                    try:
                        parsed = await self._run_strategy(strategy, request.schema_model, messages)
                        _metric_inc(
                            "structured_output_success_total",
                            {"tier": request.tier.value, "strategy": strategy.value},
                        )
                        return self._result(
                            request=request,
                            start=start,
                            attempts=attempts,
                            strategy=strategy,
                            stop_reason=StopReason.SUCCESS,
                            parsed=parsed,
                        )
                    except StructuredRefusalError as exc:
                        _metric_inc(
                            "structured_output_refusals_total",
                            {"tier": request.tier.value, "strategy": strategy.value},
                        )
                        return self._result(
                            request=request,
                            start=start,
                            attempts=attempts,
                            strategy=strategy,
                            stop_reason=StopReason.REFUSAL,
                            error_type=ErrorCategory.SAFETY,
                            refusal_message=str(exc),
                        )
                    except StructuredContentFilterError:
                        _metric_inc(
                            "structured_output_content_filter_total",
                            {"tier": request.tier.value, "strategy": strategy.value},
                        )
                        return self._result(
                            request=request,
                            start=start,
                            attempts=attempts,
                            strategy=strategy,
                            stop_reason=StopReason.CONTENT_FILTER,
                            error_type=ErrorCategory.SAFETY,
                        )
                    except StructuredTruncationError:
                        _metric_inc(
                            "structured_output_truncations_total",
                            {"tier": request.tier.value, "strategy": strategy.value},
                        )
                        if schema_attempt < request.max_schema_retries:
                            _metric_inc(
                                "structured_output_schema_retries_total",
                                {"tier": request.tier.value, "strategy": strategy.value},
                            )
                            continue
                        return self._result(
                            request=request,
                            start=start,
                            attempts=attempts,
                            strategy=strategy,
                            stop_reason=StopReason.TRUNCATED,
                            error_type=ErrorCategory.SCHEMA,
                        )
                    except StructuredSchemaValidationError as exc:
                        if schema_attempt < request.max_schema_retries:
                            _metric_inc(
                                "structured_output_schema_retries_total",
                                {"tier": request.tier.value, "strategy": strategy.value},
                            )
                            messages = self._with_schema_feedback(messages, str(exc))
                            continue
                        break
                    except StructuredOutputUnsupportedError:
                        break
                    except TimeoutError:
                        if transport_attempt < request.max_transport_retries:
                            continue
                        return self._result(
                            request=request,
                            start=start,
                            attempts=attempts,
                            strategy=strategy,
                            stop_reason=StopReason.TIMEOUT,
                            error_type=ErrorCategory.TIMEOUT,
                        )
                    except Exception as exc:
                        if self._is_transport_error(exc) and transport_attempt < request.max_transport_retries:
                            continue
                        break

        return self._result(
            request=request,
            start=start,
            attempts=max(attempts, 1),
            strategy=strategies[-1],
            stop_reason=StopReason.SCHEMA_INVALID,
            error_type=ErrorCategory.SCHEMA,
        )

    def _candidate_strategies(
        self,
        *,
        tier: OutputTier,
        model_name: str,
        capabilities: ProviderCapabilities,
        profile: SchemaComplexityProfile,
    ) -> list[StructuredOutputStrategy]:
        model_lower = model_name.lower()
        is_anthropic = model_lower.startswith("claude")

        if tier == OutputTier.A and not profile.is_strict_eligible:
            return [StructuredOutputStrategy.UNSUPPORTED]

        if tier == OutputTier.A:
            if is_anthropic and capabilities.json_schema:
                return [StructuredOutputStrategy.ANTHROPIC_OUTPUT_CONFIG]
            if capabilities.json_schema:
                return [StructuredOutputStrategy.OPENAI_STRICT_JSON_SCHEMA]
            return [StructuredOutputStrategy.UNSUPPORTED]

        if tier == OutputTier.B:
            strategies: list[StructuredOutputStrategy] = []
            if is_anthropic and capabilities.json_schema:
                strategies.append(StructuredOutputStrategy.ANTHROPIC_OUTPUT_CONFIG)
            elif capabilities.json_schema:
                strategies.append(StructuredOutputStrategy.OPENAI_STRICT_JSON_SCHEMA)
            if capabilities.tool_use:
                strategies.append(StructuredOutputStrategy.INSTRUCTOR_MD_JSON)
            return strategies or [StructuredOutputStrategy.INSTRUCTOR_MD_JSON]

        # Tier C
        if capabilities.json_object:
            return [StructuredOutputStrategy.LENIENT_JSON_OBJECT, StructuredOutputStrategy.PROMPT_BASED_JSON]
        return [StructuredOutputStrategy.PROMPT_BASED_JSON]

    async def _run_strategy(
        self,
        strategy: StructuredOutputStrategy,
        model: type[T],
        messages: list[dict[str, Any]],
    ) -> T:
        if strategy in {
            StructuredOutputStrategy.ANTHROPIC_OUTPUT_CONFIG,
            StructuredOutputStrategy.OPENAI_STRICT_JSON_SCHEMA,
            StructuredOutputStrategy.OPENAI_STRICT_FUNCTION,
            StructuredOutputStrategy.INSTRUCTOR_JSON_SCHEMA,
            StructuredOutputStrategy.INSTRUCTOR_TOOLS_STRICT,
        }:
            try:
                return await self._llm.ask_structured(messages=messages, response_model=model)
            except StructuredOutputError:
                raise
            except ValidationError as exc:
                raise StructuredSchemaValidationError(str(exc)) from exc

        if strategy == StructuredOutputStrategy.LENIENT_JSON_OBJECT:
            response = await self._llm.ask(messages=messages, response_format={"type": "json_object"})
            return self._parse_model_from_response(model, response)

        if strategy in {StructuredOutputStrategy.INSTRUCTOR_MD_JSON, StructuredOutputStrategy.PROMPT_BASED_JSON}:
            response = await self._llm.ask(messages=messages)
            return self._parse_model_from_response(model, response)

        raise StructuredOutputUnsupportedError(f"Unsupported strategy: {strategy}")

    def _parse_model_from_response(self, model: type[T], response: dict[str, Any]) -> T:
        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            raise StructuredSchemaValidationError("No JSON content in response")

        json_text = extract_json_text(content) or content
        try:
            return model.model_validate_json(json_text)
        except ValidationError as exc:
            raise StructuredSchemaValidationError(str(exc)) from exc
        except Exception as exc:
            raise StructuredSchemaValidationError(f"Failed to parse JSON response: {exc}") from exc

    @staticmethod
    def _with_schema_feedback(messages: list[dict[str, Any]], error: str) -> list[dict[str, Any]]:
        return [
            *messages,
            {
                "role": "user",
                "content": (
                    "Your previous response failed schema validation. "
                    f"Fix the JSON and return only valid JSON. Error: {error}"
                ),
            },
        ]

    @staticmethod
    def _is_transport_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(
            token in text
            for token in ("rate limit", "connection", "timeout", "temporarily unavailable", "service unavailable")
        )

    @staticmethod
    def _result(
        *,
        request: StructuredOutputRequest[T],
        start: float,
        attempts: int,
        strategy: StructuredOutputStrategy,
        stop_reason: StopReason,
        parsed: T | None = None,
        refusal_message: str | None = None,
        error_type: ErrorCategory | None = None,
    ) -> StructuredOutputResult[T]:
        return StructuredOutputResult(
            parsed=parsed,
            strategy_used=strategy,
            stop_reason=stop_reason,
            refusal_message=refusal_message,
            error_type=error_type,
            attempts=attempts,
            latency_ms=(time.monotonic() - start) * 1000,
            request_id=request.request_id,
            tier=request.tier,
        )
