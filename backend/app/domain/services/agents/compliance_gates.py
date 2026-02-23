"""
Output compliance gates for quality assurance.

Provides quality gates that block final responses if critical
quality issues are detected, ensuring consistent output standards.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GateStatus(str, Enum):
    """Gate check result status."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class GateResult:
    """Result of a compliance gate check."""

    gate_name: str
    status: GateStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def is_blocking(self) -> bool:
        """Check if this result should block output delivery."""
        return self.status == GateStatus.FAILED


@dataclass
class ComplianceReport:
    """Aggregated report from all compliance gates."""

    results: list[GateResult] = field(default_factory=list)
    passed: bool = True
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_result(self, result: GateResult) -> None:
        """Add a gate result to the report."""
        self.results.append(result)
        if result.is_blocking():
            self.passed = False
            self.blocking_issues.append(f"{result.gate_name}: {result.message}")
        elif result.status == GateStatus.WARNING:
            self.warnings.append(f"{result.gate_name}: {result.message}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "blocking_issues": self.blocking_issues,
            "warnings": self.warnings,
            "results": [{"gate": r.gate_name, "status": r.status.value, "message": r.message} for r in self.results],
        }


class ComplianceGates:
    """
    Output quality gates to block final responses with critical issues.

    Gates:
    - Artifact hygiene: No duplicate files, consistent naming
    - Command context: Shell vs IN_APP commands properly labeled
    - Source labeling: Official vs community sources identified
    - Content completeness: Required sections present
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize compliance gates.

        Args:
            strict_mode: If True, warnings become blocking failures
        """
        self._strict_mode = strict_mode

    def check_all(
        self, content: str, artifacts: list[dict[str, Any]] | None = None, sources: list[dict[str, Any]] | None = None
    ) -> ComplianceReport:
        """Run all compliance gates on the output.

        Args:
            content: The output content to check
            artifacts: List of artifact dictionaries (files, etc.)
            sources: List of source dictionaries (URLs, citations)

        Returns:
            ComplianceReport with all gate results
        """
        report = ComplianceReport()

        # Run individual gates
        gate_results = [
            self.check_artifact_hygiene(artifacts or []),
            self.check_command_context(content),
            self.check_source_labeling(sources or []),
            self.check_content_completeness(content),
        ]

        for result in gate_results:
            if self._strict_mode and result.status == GateStatus.WARNING:
                result = GateResult(
                    gate_name=result.gate_name,
                    status=GateStatus.FAILED,
                    message=result.message,
                    details=result.details,
                )
            report.add_result(result)

        return report

    def check_artifact_hygiene(self, artifacts: list[dict[str, Any]]) -> GateResult:
        """Check artifact quality: no duplicates, valid paths.

        Args:
            artifacts: List of artifact dictionaries with 'path' and optional 'type'

        Returns:
            GateResult with hygiene check status
        """
        if not artifacts:
            return GateResult(gate_name="artifact_hygiene", status=GateStatus.SKIPPED, message="No artifacts to check")

        issues = []
        seen_paths: set[str] = set()
        seen_names: set[str] = set()

        for artifact in artifacts:
            path = artifact.get("path", "")

            # Check for duplicate paths
            if path in seen_paths:
                issues.append(f"Duplicate artifact path: {path}")
            seen_paths.add(path)

            # Extract filename and check for duplicates
            name = path.split("/")[-1] if "/" in path else path
            if name in seen_names:
                issues.append(f"Duplicate filename: {name}")
            seen_names.add(name)

            # Check for invalid path characters
            if any(c in path for c in ["<", ">", "|", "?", "*"]):
                issues.append(f"Invalid characters in path: {path}")

        if issues:
            return GateResult(
                gate_name="artifact_hygiene",
                status=GateStatus.FAILED if self._strict_mode else GateStatus.WARNING,
                message="; ".join(issues[:3]),
                details={"all_issues": issues},
            )

        return GateResult(
            gate_name="artifact_hygiene",
            status=GateStatus.PASSED,
            message=f"All {len(artifacts)} artifacts pass hygiene checks",
        )

    def check_command_context(self, content: str) -> GateResult:
        """Check that commands have proper context labels.

        Ensures shell commands vs in-app instructions are clear.

        Args:
            content: The output content

        Returns:
            GateResult with command context check status
        """
        issues = []

        # Look for code blocks with commands
        code_blocks = re.findall(r"```(\w*)\n(.*?)```", content, re.DOTALL)

        for lang, block in code_blocks:
            # Check for shell commands without language specifier
            if not lang:
                # Heuristic: looks like shell commands
                shell_indicators = ["$", "npm ", "pip ", "git ", "cd ", "mkdir ", "curl "]
                if any(ind in block for ind in shell_indicators):
                    issues.append("Code block with shell commands lacks language tag (bash/sh)")

        # Check for mixed contexts in single blocks
        for lang, block in code_blocks:
            if lang in ["bash", "sh", "shell"] and "function " in block and "export " not in block:
                # Check for non-shell content
                issues.append("JavaScript-like code in bash block")

        if issues:
            return GateResult(
                gate_name="command_context",
                status=GateStatus.WARNING,
                message="; ".join(issues[:3]),
                details={"all_issues": issues},
            )

        return GateResult(
            gate_name="command_context", status=GateStatus.PASSED, message="Command contexts are properly labeled"
        )

    def check_source_labeling(self, sources: list[dict[str, Any]]) -> GateResult:
        """Check that sources are properly labeled (official vs community).

        Args:
            sources: List of source dictionaries with 'url' and optional 'type'

        Returns:
            GateResult with source labeling check status
        """
        if not sources:
            return GateResult(gate_name="source_labeling", status=GateStatus.SKIPPED, message="No sources to check")

        unlabeled = []
        official_domains = {
            "docs.",
            "developer.",
            "learn.",
            "api.",
            "github.com",
            "gitlab.com",
            "npmjs.com",
            "pypi.org",
        }

        for source in sources:
            url = source.get("url", "")
            source_type = source.get("type")

            # Check if type is specified
            if not source_type:
                # Try to infer type from URL
                is_official = any(od in url.lower() for od in official_domains)
                if not is_official:
                    unlabeled.append(url[:50])

        if unlabeled:
            return GateResult(
                gate_name="source_labeling",
                status=GateStatus.WARNING,
                message=f"{len(unlabeled)} source(s) lack type labels",
                details={"unlabeled_sources": unlabeled[:5]},
            )

        return GateResult(
            gate_name="source_labeling",
            status=GateStatus.PASSED,
            message=f"All {len(sources)} sources are properly labeled",
        )

    def check_content_completeness(self, content: str) -> GateResult:
        """Check for content completeness indicators.

        Args:
            content: The output content

        Returns:
            GateResult with completeness check status
        """
        issues = []

        # Strip fenced code blocks before scanning for markers — markers
        # inside code (TODO, FIXME, TBD) are normal developer content,
        # not indicators of an incomplete report.
        stripped_content = re.sub(r"```[\s\S]*?```", "", content)
        stripped_lower = stripped_content.lower()

        # Check for incomplete markers (only in prose, outside code blocks)
        incomplete_markers = [
            "[placeholder]",
            "coming soon",
            "to be added",
            "insert here",
        ]

        for marker in incomplete_markers:
            if marker.lower() in stripped_lower:
                issues.append(f"Incomplete marker found: {marker}")

        # Ellipsis (`...`) is extremely common in legitimate markdown —
        # only flag it at a high threshold (5+) outside code blocks.
        if stripped_lower.count("...") >= 5:
            issues.append("Excessive ellipsis markers")

        # Odd number of fences means an unclosed (truncated) code block.
        fence_count = len(re.findall(r"^```", content, re.MULTILINE))
        if fence_count % 2 != 0:
            issues.append("Possible truncated code block")

        if issues:
            return GateResult(
                gate_name="content_completeness",
                status=GateStatus.WARNING,
                message="; ".join(issues[:3]),
                details={"all_issues": issues},
            )

        return GateResult(
            gate_name="content_completeness", status=GateStatus.PASSED, message="Content appears complete"
        )


# Singleton for global access
_compliance_gates: ComplianceGates | None = None


def get_compliance_gates() -> ComplianceGates:
    """Get or create the global compliance gates instance.

    Note: strict_mode escalation is handled by check_all() or by the
    caller (e.g. _run_delivery_integrity_gate) — the singleton is
    always constructed with strict_mode=False.
    """
    global _compliance_gates
    if _compliance_gates is None:
        _compliance_gates = ComplianceGates(strict_mode=False)
    return _compliance_gates
