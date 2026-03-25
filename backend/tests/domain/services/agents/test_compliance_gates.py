"""Tests for ComplianceGates — output quality gate checks."""

from app.domain.services.agents.compliance_gates import (
    ComplianceGates,
    ComplianceReport,
    GateResult,
    GateStatus,
    get_compliance_gates,
)


# ── GateResult ──────────────────────────────────────────────────────

class TestGateResult:
    def test_failed_is_blocking(self):
        result = GateResult(gate_name="test", status=GateStatus.FAILED, message="bad")
        assert result.is_blocking() is True

    def test_warning_is_not_blocking(self):
        result = GateResult(gate_name="test", status=GateStatus.WARNING, message="warn")
        assert result.is_blocking() is False

    def test_passed_is_not_blocking(self):
        result = GateResult(gate_name="test", status=GateStatus.PASSED, message="ok")
        assert result.is_blocking() is False

    def test_skipped_is_not_blocking(self):
        result = GateResult(gate_name="test", status=GateStatus.SKIPPED, message="skip")
        assert result.is_blocking() is False


# ── ComplianceReport ────────────────────────────────────────────────

class TestComplianceReport:
    def test_empty_report_passes(self):
        report = ComplianceReport()
        assert report.passed is True
        assert report.blocking_issues == []
        assert report.warnings == []

    def test_add_passed_result(self):
        report = ComplianceReport()
        report.add_result(GateResult(gate_name="g", status=GateStatus.PASSED, message="ok"))
        assert report.passed is True
        assert len(report.results) == 1

    def test_add_failed_result_blocks(self):
        report = ComplianceReport()
        report.add_result(GateResult(gate_name="g", status=GateStatus.FAILED, message="bad"))
        assert report.passed is False
        assert "g: bad" in report.blocking_issues

    def test_add_warning_result(self):
        report = ComplianceReport()
        report.add_result(GateResult(gate_name="g", status=GateStatus.WARNING, message="warn"))
        assert report.passed is True
        assert "g: warn" in report.warnings

    def test_to_dict(self):
        report = ComplianceReport()
        report.add_result(GateResult(gate_name="g", status=GateStatus.PASSED, message="ok"))
        d = report.to_dict()
        assert d["passed"] is True
        assert len(d["results"]) == 1
        assert d["results"][0]["gate"] == "g"
        assert d["results"][0]["status"] == "passed"


# ── Artifact Hygiene Gate ───────────────────────────────────────────

class TestArtifactHygiene:
    def test_skipped_when_no_artifacts(self):
        gates = ComplianceGates()
        result = gates.check_artifact_hygiene([])
        assert result.status == GateStatus.SKIPPED

    def test_passes_for_clean_artifacts(self):
        gates = ComplianceGates()
        artifacts = [
            {"path": "output/report.pdf"},
            {"path": "output/data.csv"},
        ]
        result = gates.check_artifact_hygiene(artifacts)
        assert result.status == GateStatus.PASSED
        assert "2 artifacts" in result.message

    def test_warns_on_duplicate_paths(self):
        gates = ComplianceGates()
        artifacts = [
            {"path": "output/report.pdf"},
            {"path": "output/report.pdf"},
        ]
        result = gates.check_artifact_hygiene(artifacts)
        assert result.status == GateStatus.WARNING
        assert "Duplicate artifact path" in result.message

    def test_warns_on_duplicate_filenames(self):
        gates = ComplianceGates()
        artifacts = [
            {"path": "dir_a/report.pdf"},
            {"path": "dir_b/report.pdf"},
        ]
        result = gates.check_artifact_hygiene(artifacts)
        assert result.status == GateStatus.WARNING
        assert "Duplicate filename" in result.message

    def test_warns_on_invalid_path_chars(self):
        gates = ComplianceGates()
        artifacts = [{"path": "output/<report>.pdf"}]
        result = gates.check_artifact_hygiene(artifacts)
        assert result.status == GateStatus.WARNING
        assert "Invalid characters" in result.message

    def test_strict_mode_promotes_warning_to_failure(self):
        gates = ComplianceGates(strict_mode=True)
        artifacts = [
            {"path": "output/report.pdf"},
            {"path": "output/report.pdf"},
        ]
        result = gates.check_artifact_hygiene(artifacts)
        assert result.status == GateStatus.FAILED


# ── Command Context Gate ────────────────────────────────────────────

class TestCommandContext:
    def test_passes_clean_content(self):
        gates = ComplianceGates()
        content = "Here is the analysis with no code blocks."
        result = gates.check_command_context(content)
        assert result.status == GateStatus.PASSED

    def test_passes_labeled_code_blocks(self):
        gates = ComplianceGates()
        content = "Run this:\n```bash\ngit status\n```"
        result = gates.check_command_context(content)
        assert result.status == GateStatus.PASSED

    def test_warns_unlabeled_shell_commands(self):
        gates = ComplianceGates()
        content = "Run this:\n```\nnpm install express\n```"
        result = gates.check_command_context(content)
        assert result.status == GateStatus.WARNING
        assert "lacks language tag" in result.message

    def test_warns_js_in_bash_block(self):
        gates = ComplianceGates()
        content = "```bash\nfunction greet() { return 'hi'; }\n```"
        result = gates.check_command_context(content)
        assert result.status == GateStatus.WARNING
        assert "JavaScript-like" in result.message

    def test_no_false_positive_for_bash_functions_with_export(self):
        gates = ComplianceGates()
        content = "```bash\nexport MY_VAR=1\nfunction setup() { echo $MY_VAR; }\n```"
        result = gates.check_command_context(content)
        # "function " is present but "export " is also present → no warning
        assert result.status == GateStatus.PASSED


# ── Source Labeling Gate ────────────────────────────────────────────

class TestSourceLabeling:
    def test_skipped_when_no_sources(self):
        gates = ComplianceGates()
        result = gates.check_source_labeling([])
        assert result.status == GateStatus.SKIPPED

    def test_passes_labeled_sources(self):
        gates = ComplianceGates()
        sources = [
            {"url": "https://blog.example.com/post", "type": "community"},
            {"url": "https://docs.python.org", "type": "official"},
        ]
        result = gates.check_source_labeling(sources)
        assert result.status == GateStatus.PASSED

    def test_passes_official_domains_without_type(self):
        gates = ComplianceGates()
        sources = [
            {"url": "https://docs.python.org/3/tutorial"},
            {"url": "https://github.com/python/cpython"},
            {"url": "https://pypi.org/project/requests"},
        ]
        result = gates.check_source_labeling(sources)
        assert result.status == GateStatus.PASSED

    def test_warns_unlabeled_non_official(self):
        gates = ComplianceGates()
        sources = [
            {"url": "https://random-blog.com/how-to-python"},
        ]
        result = gates.check_source_labeling(sources)
        assert result.status == GateStatus.WARNING
        assert "1 source(s) lack type labels" in result.message

    def test_mixed_labeled_and_unlabeled(self):
        gates = ComplianceGates()
        sources = [
            {"url": "https://docs.python.org", "type": "official"},
            {"url": "https://myblog.io/post", },
            {"url": "https://forum.io/thread", },
        ]
        result = gates.check_source_labeling(sources)
        assert result.status == GateStatus.WARNING
        assert "2 source(s)" in result.message


# ── Content Completeness Gate ───────────────────────────────────────

class TestContentCompleteness:
    def test_passes_complete_content(self):
        gates = ComplianceGates()
        content = "This is a fully complete report with all sections."
        result = gates.check_content_completeness(content)
        assert result.status == GateStatus.PASSED

    def test_warns_on_placeholder_marker(self):
        gates = ComplianceGates()
        content = "Section 1\n[placeholder]\nSection 2"
        result = gates.check_content_completeness(content)
        assert result.status == GateStatus.WARNING
        assert "Incomplete marker" in result.message

    def test_warns_on_coming_soon(self):
        gates = ComplianceGates()
        content = "This feature is coming soon in a future update."
        result = gates.check_content_completeness(content)
        assert result.status == GateStatus.WARNING

    def test_warns_on_to_be_added(self):
        gates = ComplianceGates()
        content = "More details to be added later."
        result = gates.check_content_completeness(content)
        assert result.status == GateStatus.WARNING

    def test_warns_on_insert_here(self):
        gates = ComplianceGates()
        content = "Methodology: insert here the details."
        result = gates.check_content_completeness(content)
        assert result.status == GateStatus.WARNING

    def test_warns_on_excessive_ellipsis(self):
        gates = ComplianceGates()
        content = "Point 1... Point 2... Point 3... Point 4... Point 5..."
        result = gates.check_content_completeness(content)
        assert result.status == GateStatus.WARNING
        assert "ellipsis" in result.message.lower()

    def test_no_false_positive_for_few_ellipsis(self):
        gates = ComplianceGates()
        content = "He paused... then continued... and finished."
        result = gates.check_content_completeness(content)
        # Only 3 ellipsis, threshold is 5
        assert result.status == GateStatus.PASSED

    def test_warns_on_truncated_code_block(self):
        gates = ComplianceGates()
        content = "Here is code:\n```python\ndef foo():\n    pass"
        result = gates.check_content_completeness(content)
        assert result.status == GateStatus.WARNING
        assert "truncated" in result.message.lower()

    def test_ignores_markers_inside_code_blocks(self):
        gates = ComplianceGates()
        content = "Report:\n```python\n# TODO: placeholder for later\n```\nEnd."
        result = gates.check_content_completeness(content)
        # "placeholder" is inside code block, should not trigger
        assert result.status == GateStatus.PASSED


# ── check_all Integration ──────────────────────────────────────────

class TestCheckAll:
    def test_all_pass_clean_input(self):
        gates = ComplianceGates()
        report = gates.check_all(
            content="Complete analysis with proper formatting.",
            artifacts=[{"path": "output/report.pdf"}],
            sources=[{"url": "https://docs.python.org", "type": "official"}],
        )
        assert report.passed is True
        assert len(report.blocking_issues) == 0

    def test_collects_multiple_warnings(self):
        gates = ComplianceGates()
        report = gates.check_all(
            content="```\nnpm install\n```\nMore coming soon.",
            artifacts=[{"path": "a.txt"}, {"path": "a.txt"}],
            sources=[{"url": "https://random.io/post"}],
        )
        assert len(report.warnings) >= 2

    def test_strict_mode_promotes_all_warnings_to_failures(self):
        gates = ComplianceGates(strict_mode=True)
        report = gates.check_all(
            content="```\nnpm install\n```",
            artifacts=[],
            sources=[],
        )
        # Strict mode: command context warning → failure
        failed_gates = [r for r in report.results if r.status == GateStatus.FAILED]
        if any(r.status == GateStatus.WARNING for r in ComplianceGates().check_all(content="```\nnpm install\n```").results):
            assert len(failed_gates) >= 1

    def test_no_artifacts_or_sources(self):
        gates = ComplianceGates()
        report = gates.check_all(content="Simple text.")
        assert report.passed is True
        # Artifact and source gates should be SKIPPED
        skipped = [r for r in report.results if r.status == GateStatus.SKIPPED]
        assert len(skipped) == 2


# ── Singleton ───────────────────────────────────────────────────────

class TestSingleton:
    def test_get_compliance_gates_returns_instance(self):
        gates = get_compliance_gates()
        assert isinstance(gates, ComplianceGates)

    def test_get_compliance_gates_is_stable(self):
        g1 = get_compliance_gates()
        g2 = get_compliance_gates()
        assert g1 is g2
