"""Tests for phantom citation removal when has_sources=False (Fix 2)."""


def test_no_source_prompt_has_no_numbered_citations():
    """When has_sources=False, the prompt must not contain [1] or [2] fake markers."""
    from app.domain.services.prompts.execution import build_summarize_prompt

    prompt = build_summarize_prompt(
        has_sources=False,
    )
    # Must NOT contain fake citation markers
    assert "[1] Source Name - URL" not in prompt
    assert "[2] Source Name - URL" not in prompt


def test_no_source_prompt_has_no_reference_section():
    """When has_sources=False, no MANDATORY References header should appear."""
    from app.domain.services.prompts.execution import build_summarize_prompt

    prompt = build_summarize_prompt(
        has_sources=False,
    )
    assert "Do NOT include a References section" in prompt or "No external sources" in prompt


def test_has_sources_prompt_keeps_references():
    """When has_sources=True, the References section should remain."""
    from app.domain.services.prompts.execution import build_summarize_prompt

    prompt = build_summarize_prompt(
        has_sources=True,
    )
    assert "References" in prompt
    assert "List ALL cited sources" in prompt
