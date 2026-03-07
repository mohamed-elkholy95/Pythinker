"""Tests for plain, professional summarize prompt formatting."""

from __future__ import annotations

from app.domain.services.prompts.execution import (
    STREAMING_SUMMARIZE_PROMPT,
    build_summarize_prompt,
)


def test_build_summarize_prompt_uses_plain_headings() -> None:
    prompt = build_summarize_prompt(has_sources=False, research_depth="STANDARD")

    assert "# [Clear, Descriptive Title]" in prompt
    assert "## [Main Section 1]" in prompt
    assert "## [Main Section 2]" in prompt
    assert "# 🔬" not in prompt
    assert "## 📊" not in prompt
    assert "## 🔍" not in prompt


def test_build_summarize_prompt_does_not_request_emoji_headings() -> None:
    prompt = build_summarize_prompt(
        has_sources=True,
        source_list="[1] Example Source - https://example.com",
        research_depth="STANDARD",
    )

    assert "Use emoji prefixes on section headings" not in prompt
    assert "## 🎯 Section" not in prompt
    assert "## 💡 Insights" not in prompt
    assert "## 🏆 Results" not in prompt


def test_streaming_summarize_prompt_is_plain_text_format() -> None:
    assert "# 🔬" not in STREAMING_SUMMARIZE_PROMPT
    assert "## 📊" not in STREAMING_SUMMARIZE_PROMPT
    assert "## 🔍" not in STREAMING_SUMMARIZE_PROMPT
    assert "Use emoji prefixes on section headings" not in STREAMING_SUMMARIZE_PROMPT
