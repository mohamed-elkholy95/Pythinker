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


def test_summarize_prompt_includes_artifact_section_in_canonical_structure() -> None:
    """When artifact_references are provided, ## Artifact References appears
    between ## Conclusion and ## References in the template."""
    prompt = build_summarize_prompt(
        has_sources=True,
        source_list="[1] Source A - https://a.example",
        research_depth="STANDARD",
        artifact_references=[
            {"filename": "report-fixed-id.md", "content_type": "text/markdown"},
            {"filename": "chart.png", "content_type": "image/png"},
        ],
    )

    assert "## Artifact References" in prompt
    # The artifact section must appear before the template's "## References (MANDATORY"
    assert prompt.index("## Artifact References") < prompt.index("## References (MANDATORY")
    assert "`report-fixed-id.md`" in prompt
    assert "`chart.png`" in prompt


def test_summarize_prompt_counts_numbered_sources_not_raw_lines() -> None:
    """Multiline titles should not inflate the source count."""
    source_list = (
        "[1] Source Title Line 1\n"
        "Continuation of title - https://one.example\n"
        "[2] Source Two - https://two.example\n"
    )

    prompt = build_summarize_prompt(
        has_sources=True,
        source_list=source_list,
        research_depth="STANDARD",
    )

    assert "exactly 2 sources available" in prompt


def test_summarize_prompt_omits_artifact_section_when_no_artifacts() -> None:
    """Without artifact_references, no artifact section appears in the prompt."""
    prompt = build_summarize_prompt(
        has_sources=True,
        source_list="[1] Source A - https://a.example",
        research_depth="STANDARD",
    )

    assert "## Artifact References" not in prompt
