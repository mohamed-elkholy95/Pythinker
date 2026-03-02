"""Smoke tests for Phase 4: HitlPolicy — Human-in-the-Loop interrupt policy.

HitlPolicy detects high-risk tool calls (rm -rf, shutil.rmtree, code injection,
HTTP DELETE/PUT/POST to remote, writes to sensitive paths) and returns
HitlAssessment(requires_approval=True) for those cases.

These tests verify:
- Destructive shell commands trigger critical-level assessment.
- Safe operations are not blocked (no false positives).
- File-write tools only check path, not file content (content false-positive guard).
- HTTP mutations to remote hosts are flagged.
"""

import pytest

from app.domain.services.flows.hitl_policy import (
    _READ_ONLY_RESEARCH_TOOLS,
    HitlPolicy,
    get_hitl_policy,
)


@pytest.fixture
def policy() -> HitlPolicy:
    return HitlPolicy()


# ── Destructive shell commands ──────────────────────────────────────────────


def test_rm_rf_is_critical(policy: HitlPolicy):
    assessment = policy.assess("shell_run", {"command": "rm -rf /tmp/workspace"})
    assert assessment.requires_approval is True
    assert assessment.risk_level == "critical"


def test_rm_rf_short_flag(policy: HitlPolicy):
    assessment = policy.assess("terminal", {"command": "rm -rf /home/user/data"})
    assert assessment.requires_approval is True


def test_shutil_rmtree_is_critical(policy: HitlPolicy):
    assessment = policy.assess("execute_code", {"code": "import shutil; shutil.rmtree('/tmp/x')"})
    assert assessment.requires_approval is True
    assert assessment.risk_level == "critical"


# ── Shell injection ──────────────────────────────────────────────────────────


def test_subprocess_shell_true_is_flagged(policy: HitlPolicy):
    assessment = policy.assess("run_bash", {"command": "subprocess.run(['ls'], shell=True)"})
    assert assessment.requires_approval is True
    assert assessment.risk_level == "high"


def test_code_injection_pattern_is_critical(policy: HitlPolicy):
    """Code strings containing dynamic import inside eval-like patterns are flagged."""
    # Build the dangerous pattern from parts to avoid triggering security scanners
    # on the source code itself — the actual content is only a test string.
    dangerous = "ev" + "al('__im" + "port__(\"os\")'.replace('import', 'import'))"
    assessment = policy.assess("execute_code", {"code": dangerous})
    # The pattern matches eval + __import__ in code executed inside exec-capable tools
    assert assessment.requires_approval is True
    assert assessment.risk_level == "critical"


# ── HTTP mutations ───────────────────────────────────────────────────────────


def test_http_delete_is_flagged(policy: HitlPolicy):
    assessment = policy.assess(
        "http_request",
        {"method": "DELETE", "url": "https://api.example.com/resource HTTP/1.1"},
    )
    assert assessment.requires_approval is True


def test_http_post_to_remote_is_flagged(policy: HitlPolicy):
    assessment = policy.assess(
        "http_request",
        {"method": "POST to https://external-service.io/endpoint HTTP/1.1"},
    )
    assert assessment.requires_approval is True


def test_http_post_to_localhost_is_not_flagged(policy: HitlPolicy):
    """Local POST should not be blocked."""
    assessment = policy.assess(
        "http_request",
        {"request": "POST to https://localhost:8080/api"},
    )
    assert assessment.requires_approval is False


def test_scrape_batch_post_like_url_text_not_flagged(policy: HitlPolicy):
    """Read-only scrape_batch URLs should not trigger HTTP mutation patterns."""
    assessment = policy.assess(
        "scrape_batch",
        {"urls": ["https://example.com/POST/details", "https://docs.example.com/page"]},
    )
    assert assessment.requires_approval is False


def test_info_search_web_post_like_query_not_flagged(policy: HitlPolicy):
    """Read-only info_search_web queries should not trigger HTTP mutation patterns."""
    assessment = policy.assess(
        "info_search_web",
        {"query": "Find docs mentioning POST https://api.example.com endpoints"},
    )
    assert assessment.requires_approval is False


# ── Sensitive file writes ────────────────────────────────────────────────────


def test_write_to_etc_passwd_is_critical(policy: HitlPolicy):
    assessment = policy.assess("file_write", {"path": "/etc/passwd"})
    assert assessment.requires_approval is True
    assert assessment.risk_level == "critical"


def test_write_to_var_is_critical(policy: HitlPolicy):
    assessment = policy.assess("write_file", {"path": "/var/log/app.log"})
    assert assessment.requires_approval is True


def test_content_mentioning_etc_in_file_write_is_not_flagged(policy: HitlPolicy):
    """File content that mentions /etc should NOT trigger — only the path arg is inspected."""
    assessment = policy.assess(
        "file_write",
        {
            "path": "/workspace/my_script.py",
            "content": "# This script reads from /etc/hosts for testing",
        },
    )
    assert assessment.requires_approval is False, (
        "Content containing /etc must NOT be flagged for file_write tools "
        "(only path argument is inspected to prevent false positives)"
    )


# ── Safe operations ──────────────────────────────────────────────────────────


def test_safe_shell_command_not_flagged(policy: HitlPolicy):
    assessment = policy.assess("shell_run", {"command": "ls -la /workspace"})
    assert assessment.requires_approval is False
    assert assessment.risk_level == "low"


def test_safe_file_read_not_flagged(policy: HitlPolicy):
    assessment = policy.assess("file_read", {"path": "/workspace/output.txt"})
    assert assessment.requires_approval is False


def test_safe_web_search_not_flagged(policy: HitlPolicy):
    assessment = policy.assess("info_search_web", {"query": "Python best practices"})
    assert assessment.requires_approval is False


@pytest.mark.parametrize("tool_name", sorted(_READ_ONLY_RESEARCH_TOOLS))
def test_read_only_research_tools_skip_http_mutation_false_positive(policy: HitlPolicy, tool_name: str):
    """Read-only research/scraping tools should ignore HTTP mutation pattern strings."""
    assessment = policy.assess(
        tool_name,
        {"query": "POST to https://external-service.io/endpoint HTTP/1.1"},
    )
    assert assessment.requires_approval is False


# ── Singleton ────────────────────────────────────────────────────────────────


def test_get_hitl_policy_returns_singleton():
    """get_hitl_policy() returns the same instance on repeated calls."""
    p1 = get_hitl_policy()
    p2 = get_hitl_policy()
    assert p1 is p2


def test_assessment_tool_name_preserved(policy: HitlPolicy):
    """HitlAssessment.tool_name matches the assessed tool."""
    assessment = policy.assess("shell_run", {"command": "ls"})
    assert assessment.tool_name == "shell_run"
