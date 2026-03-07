"""Tests for final report output sanitization."""

from __future__ import annotations

from app.domain.services.agents.report_output_sanitizer import sanitize_report_output


def test_sanitize_report_output_strips_heading_emoji_prefixes() -> None:
    content = "# 🔬 Title\n\n## 📊 Findings\n\n## 📎 Deliverables"

    result = sanitize_report_output(content)

    assert result == "# Title\n\n## Findings\n\n## Deliverables"


def test_sanitize_report_output_strips_notice_emoji_prefixes() -> None:
    content = "> ⚠️ **Incomplete Report:** Body"

    result = sanitize_report_output(content)

    assert result == "> **Incomplete Report:** Body"


def test_sanitize_report_output_preserves_code_fences() -> None:
    content = "```markdown\n# 🔬 Leave this example alone\n```"

    result = sanitize_report_output(content)

    assert result == content
