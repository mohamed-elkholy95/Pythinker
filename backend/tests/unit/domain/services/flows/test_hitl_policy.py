"""Tests for HitlPolicy — Human-in-the-Loop risk assessment."""

from __future__ import annotations

from app.domain.services.flows.hitl_policy import (
    HitlAssessment,
    HitlPolicy,
    get_hitl_policy,
)


class TestHitlAssessment:
    """Tests for HitlAssessment dataclass."""

    def test_default_values(self) -> None:
        assessment = HitlAssessment(tool_name="test", requires_approval=False)
        assert assessment.reason == ""
        assert assessment.risk_level == "low"
        assert assessment.matched_pattern == ""

    def test_with_all_fields(self) -> None:
        assessment = HitlAssessment(
            tool_name="shell_run",
            requires_approval=True,
            reason="destructive command",
            risk_level="critical",
            matched_pattern=r"\brm\s+",
        )
        assert assessment.requires_approval is True
        assert assessment.risk_level == "critical"


class TestHitlPolicyDestructiveCommands:
    """Tests for destructive shell command detection."""

    def setup_method(self) -> None:
        self.policy = HitlPolicy()

    def test_rm_rf_detected_in_shell_tool(self) -> None:
        result = self.policy.assess("shell_run", {"command": "rm -rf /tmp/mydir"})
        assert result.requires_approval is True
        assert result.risk_level == "critical"

    def test_rm_rf_not_detected_in_non_shell_tool(self) -> None:
        result = self.policy.assess("file_write", {"content": "rm -rf /tmp/test"})
        assert result.requires_approval is False

    def test_rmdir_absolute_path(self) -> None:
        result = self.policy.assess("terminal", {"command": "rmdir /var/data"})
        assert result.requires_approval is True

    def test_shutil_rmtree(self) -> None:
        result = self.policy.assess("execute_code", {"code": "shutil.rmtree('/data')"})
        assert result.requires_approval is True

    def test_safe_shell_command(self) -> None:
        result = self.policy.assess("shell_run", {"command": "ls -la /tmp"})
        assert result.requires_approval is False

    def test_echo_command_safe(self) -> None:
        result = self.policy.assess("terminal", {"command": "echo hello world"})
        assert result.requires_approval is False


class TestHitlPolicyShellInjection:
    """Tests for shell injection pattern detection."""

    def setup_method(self) -> None:
        self.policy = HitlPolicy()

    def test_os_system_detected(self) -> None:
        result = self.policy.assess("execute_code", {"code": "os.system('ls')"})
        assert result.requires_approval is True

    def test_subprocess_shell_true(self) -> None:
        result = self.policy.assess("shell_run", {"command": "subprocess run shell=True 'cmd'"})
        assert result.requires_approval is True

    def test_eval_import(self) -> None:
        result = self.policy.assess("execute_code", {"code": "eval(__import__('os').system('id'))"})
        assert result.requires_approval is True


class TestHitlPolicyHttpMutations:
    """Tests for external HTTP mutation detection."""

    def setup_method(self) -> None:
        self.policy = HitlPolicy()

    def test_delete_http_detected(self) -> None:
        result = self.policy.assess("run_script", {"args": "DELETE /api/users HTTP/1.1"})
        assert result.requires_approval is True

    def test_post_external_detected(self) -> None:
        result = self.policy.assess("run_script", {"args": "POST to https://example.com/api"})
        assert result.requires_approval is True

    def test_post_localhost_allowed(self) -> None:
        result = self.policy.assess("run_script", {"args": "POST to https://localhost:8000/api"})
        assert result.requires_approval is False

    def test_post_127_allowed(self) -> None:
        result = self.policy.assess("run_script", {"args": "POST to https://127.0.0.1/api"})
        assert result.requires_approval is False

    def test_research_tools_skip_http_mutations(self) -> None:
        result = self.policy.assess("web_search", {"url": "POST https://example.com/search"})
        assert result.requires_approval is False

    def test_scrape_tool_skips_http_mutations(self) -> None:
        result = self.policy.assess("scrape_url", {"url": "DELETE https://example.com/page"})
        assert result.requires_approval is False


class TestHitlPolicySensitivePaths:
    """Tests for sensitive file path detection."""

    def setup_method(self) -> None:
        self.policy = HitlPolicy()

    def test_open_etc_passwd_in_code(self) -> None:
        result = self.policy.assess("execute_code", {"code": "open('/etc/passwd', 'w')"})
        assert result.requires_approval is True

    def test_file_write_to_etc(self) -> None:
        result = self.policy.assess("file_write", {"path": "/etc/hosts", "content": "data"})
        assert result.requires_approval is True

    def test_file_write_to_var(self) -> None:
        result = self.policy.assess("file_write", {"path": "/var/log/app.log", "content": "data"})
        assert result.requires_approval is True

    def test_file_write_to_workspace_safe(self) -> None:
        result = self.policy.assess("file_write", {"path": "/workspace/output/report.md", "content": "data"})
        assert result.requires_approval is False

    def test_file_write_content_not_inspected(self) -> None:
        # Content containing dangerous patterns should NOT trigger for file_write tools
        result = self.policy.assess("file_write", {"path": "/workspace/test.py", "content": "rm -rf /"})
        assert result.requires_approval is False


class TestHitlPolicyBuildArgsText:
    """Tests for _build_args_text scoping."""

    def setup_method(self) -> None:
        self.policy = HitlPolicy()

    def test_file_write_only_inspects_path(self) -> None:
        text = HitlPolicy._build_args_text("file_write", {"path": "/safe/path", "content": "rm -rf /"})
        assert "rm -rf" not in text
        assert "/safe/path" in text

    def test_shell_tool_inspects_all_args(self) -> None:
        text = HitlPolicy._build_args_text("shell_run", {"command": "rm -rf /tmp", "env": "TEST=1"})
        assert "rm -rf" in text
        assert "TEST=1" in text

    def test_none_values_skipped(self) -> None:
        text = HitlPolicy._build_args_text("shell_run", {"command": "ls", "env": None})
        assert "None" not in text


class TestGetHitlPolicy:
    """Tests for get_hitl_policy singleton."""

    def test_returns_instance(self) -> None:
        policy = get_hitl_policy()
        assert isinstance(policy, HitlPolicy)

    def test_singleton_returns_same_instance(self) -> None:
        p1 = get_hitl_policy()
        p2 = get_hitl_policy()
        assert p1 is p2
