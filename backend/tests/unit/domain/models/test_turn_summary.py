"""Tests for TurnSummary (app.domain.models.turn_summary)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

from app.core.config_llm import LLMSettingsMixin
from app.domain.models.turn_summary import TurnSummary


class TestTurnSummary:
    def test_construction_and_asdict(self) -> None:
        summary = TurnSummary(
            iterations=3,
            tools_called=["file_read", "search"],
            prompt_tokens=100,
            completion_tokens=50,
            estimated_cost_usd=0.0123,
            duration_seconds=1.5,
        )
        assert summary.iterations == 3
        assert summary.tools_called == ["file_read", "search"]
        assert asdict(summary) == {
            "iterations": 3,
            "tools_called": ["file_read", "search"],
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "estimated_cost_usd": 0.0123,
            "duration_seconds": 1.5,
        }

    def test_frozen(self) -> None:
        summary = TurnSummary(
            iterations=1,
            tools_called=[],
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost_usd=0.0,
            duration_seconds=0.0,
        )
        try:
            summary.iterations = 2  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")  # pragma: no cover
        except FrozenInstanceError:
            pass


class TestLLMPricingDefaults:
    def test_llm_pricing_fields_present_with_safe_defaults(self) -> None:
        assert hasattr(LLMSettingsMixin, "llm_input_price_per_million")
        assert hasattr(LLMSettingsMixin, "llm_output_price_per_million")
        assert LLMSettingsMixin.llm_input_price_per_million == 0.0
        assert LLMSettingsMixin.llm_output_price_per_million == 0.0
