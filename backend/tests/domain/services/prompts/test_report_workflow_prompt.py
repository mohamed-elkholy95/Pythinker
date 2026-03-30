"""Tests for the report deliverable workflow prompt."""

from app.domain.services.prompts.execution import build_report_file_write_signal


def test_report_workflow_prompt_requires_exact_written_path_for_verification() -> None:
    prompt = build_report_file_write_signal("/workspace/session/output/reports")

    assert "exact same full path you wrote with `file_write`" in prompt
    assert "Do NOT guess alternate filenames" in prompt
    assert "If one verification command fails" in prompt


def test_report_workflow_prompt_uses_exact_path_placeholder_in_attachments_example() -> None:
    prompt = build_report_file_write_signal("/workspace/session/output/reports")

    assert '"attachments": ["<exact path passed to file_write>"]' in prompt
    assert '"/workspace/session/output/reports/report.md"' not in prompt


def test_report_workflow_prompt_suppresses_verification_retry_loop() -> None:
    """Prompt must instruct agent to stop after one verification attempt.

    This prevents the shell-command retry loop where the agent checks alternate
    filenames (report.md, report_final.md, etc.) after the first check fails.
    """
    prompt = build_report_file_write_signal("/workspace/session/output/reports")

    assert "one check is sufficient" in prompt or "one verification command" in prompt.lower()
    assert "Do NOT run `ls`, `find`, or `cat` in a loop" in prompt


def test_report_workflow_prompt_without_path_uses_generic_target() -> None:
    """Prompt generated with no path still contains required anti-loop instructions."""
    prompt = build_report_file_write_signal(None)

    assert "Do NOT guess alternate filenames" in prompt
    assert "If one verification command fails" in prompt
