"""Tests for PlanValidator and PlanValidationReport."""

from app.domain.models.plan import Plan, Step
from app.domain.services.validation.plan_validator import (
    PlanValidationReport,
    PlanValidator,
    _extract_tool_mentions,
)


class TestPlanValidationReport:
    def test_passed_no_errors(self) -> None:
        r = PlanValidationReport(errors=[], warnings=["minor thing"])
        assert r.passed is True

    def test_failed_with_errors(self) -> None:
        r = PlanValidationReport(errors=["bad thing"])
        assert r.passed is False

    def test_to_summary_no_issues(self) -> None:
        r = PlanValidationReport()
        assert "No issues" in r.to_summary()

    def test_to_summary_with_errors(self) -> None:
        r = PlanValidationReport(errors=["err1", "err2"])
        summary = r.to_summary()
        assert "err1" in summary
        assert "err2" in summary

    def test_to_summary_max_items(self) -> None:
        r = PlanValidationReport(errors=[f"err{i}" for i in range(10)])
        summary = r.to_summary(max_items=3)
        assert "err0" in summary
        assert "err9" not in summary


class TestExtractToolMentions:
    def test_tool_colon(self) -> None:
        mentions = _extract_tool_mentions("tool: web_search")
        assert "web_search" in mentions

    def test_use_tool(self) -> None:
        mentions = _extract_tool_mentions("use `browser` tool to navigate")
        assert "browser" in mentions

    def test_backtick_tool(self) -> None:
        mentions = _extract_tool_mentions("`file_read` tool")
        assert "file_read" in mentions

    def test_no_mentions(self) -> None:
        mentions = _extract_tool_mentions("Search for Python documentation")
        assert mentions == []

    def test_empty_string(self) -> None:
        assert _extract_tool_mentions("") == []


class TestPlanValidator:
    def test_valid_plan(self) -> None:
        plan = Plan(steps=[Step(id="s-0", description="Search for data online")])
        v = PlanValidator()
        report = v.validate(plan)
        assert report.passed is True

    def test_empty_plan(self) -> None:
        plan = Plan()
        v = PlanValidator()
        report = v.validate(plan)
        assert report.passed is False

    def test_unavailable_tool_warning(self) -> None:
        plan = Plan(
            steps=[Step(id="s-0", description="Use `nonexistent_tool` tool to do X")]
        )
        v = PlanValidator(tool_names=["web_search", "browser"])
        report = v.validate(plan)
        assert any("nonexistent_tool" in w for w in report.warnings)

    def test_unavailable_tool_strict_error(self) -> None:
        plan = Plan(
            steps=[Step(id="s-0", description="Use `bad_tool` tool to do X")]
        )
        v = PlanValidator(tool_names=["web_search"], strict_tool_match=True)
        report = v.validate(plan)
        assert any("bad_tool" in e for e in report.errors)

    def test_available_tool_no_warning(self) -> None:
        plan = Plan(
            steps=[Step(id="s-0", description="Use `web_search` tool to find data")]
        )
        v = PlanValidator(tool_names=["web_search"])
        report = v.validate(plan)
        assert not any("web_search" in w for w in report.warnings)

    def test_deduplication(self) -> None:
        plan = Plan(
            steps=[
                Step(id="s-0", description=""),
                Step(id="s-1", description=""),
            ]
        )
        v = PlanValidator()
        report = v.validate(plan)
        # Should have deduplicated "empty description" errors
        desc_errors = [e for e in report.errors if "empty description" in e]
        assert len(desc_errors) == 2  # Each step gets its own error (different step IDs)
