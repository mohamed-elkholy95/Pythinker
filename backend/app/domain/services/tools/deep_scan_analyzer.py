"""
Deep Scan Analyzer Tool for comprehensive code analysis.

Integrates:
- Security vulnerability detection
- Code quality metrics
- Dependency scanning

Provides unified access to all analysis capabilities via tool interface.
"""

import logging

from app.domain.models.tool_result import ToolResult
from app.domain.services.analyzers import (
    DependencyAnalyzer,
    QualityAnalyzer,
    SecurityAnalyzer,
)
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)


class DeepScanAnalyzerTool(BaseTool):
    """
    Deep code analysis tool providing security, quality, and dependency scanning.

    This tool integrates multiple analyzers to provide comprehensive code analysis:
    - SecurityAnalyzer: Detects vulnerabilities (SQL injection, XSS, hardcoded secrets, etc.)
    - QualityAnalyzer: Measures code quality (complexity, maintainability, duplication)
    - DependencyAnalyzer: Scans for outdated packages and known CVEs
    """

    name = "deep_scan"
    max_observe = 15000  # Analysis reports can be verbose

    def __init__(self, strict_mode: bool = False):
        """
        Initialize deep scan analyzer tool.

        Args:
            strict_mode: If True, use stricter detection thresholds
        """
        super().__init__()
        self._security_analyzer = SecurityAnalyzer(strict_mode=strict_mode)
        self._quality_analyzer = QualityAnalyzer()
        self._dependency_analyzer = DependencyAnalyzer()
        self._strict_mode = strict_mode

    @tool(
        name="deep_scan_code",
        description="Perform comprehensive code analysis including security, quality, and dependency scanning. Analyzes source code for vulnerabilities, measures complexity and maintainability, and checks dependencies for known issues.",
        parameters={
            "code": {"type": "string", "description": "Source code to analyze"},
            "file_path": {"type": "string", "description": "Path to the file (for reporting context)"},
            "language": {
                "type": "string",
                "description": "Programming language (python, javascript)",
                "enum": ["python", "javascript"],
            },
            "include_security": {
                "type": "boolean",
                "description": "Include security vulnerability scan",
                "default": True,
            },
            "include_quality": {"type": "boolean", "description": "Include code quality analysis", "default": True},
        },
        required=["code", "file_path", "language"],
    )
    async def deep_scan_code(
        self,
        code: str,
        file_path: str,
        language: str,
        include_security: bool = True,
        include_quality: bool = True,
    ) -> ToolResult:
        """
        Perform comprehensive code analysis.

        Args:
            code: Source code to analyze
            file_path: Path to the file
            language: Programming language
            include_security: Include security scan
            include_quality: Include quality analysis

        Returns:
            Combined analysis results
        """
        try:
            results = {
                "file_path": file_path,
                "language": language,
                "analysis_mode": "strict" if self._strict_mode else "standard",
            }
            issues_summary = []

            # Security analysis
            if include_security:
                vulnerabilities = self._security_analyzer.analyze(code, file_path, language)
                security_summary = self._security_analyzer.get_summary(vulnerabilities)
                results["security"] = {
                    "vulnerabilities": [v.to_dict() for v in vulnerabilities],
                    "summary": security_summary,
                }
                if security_summary["critical_count"] > 0:
                    issues_summary.append(f"🚨 {security_summary['critical_count']} CRITICAL security issues")
                if security_summary["high_count"] > 0:
                    issues_summary.append(f"⚠️ {security_summary['high_count']} HIGH security issues")

            # Quality analysis
            if include_quality:
                metrics, quality_issues = self._quality_analyzer.analyze(code, file_path, language)
                results["quality"] = {
                    "metrics": metrics.to_dict(),
                    "issues": [i.to_dict() for i in quality_issues],
                }
                if metrics.quality_rating.value in ["poor", "critical"]:
                    issues_summary.append(f"📉 Quality rating: {metrics.quality_rating.value.upper()}")
                critical_quality = sum(1 for i in quality_issues if i.severity == "critical")
                if critical_quality > 0:
                    issues_summary.append(f"🔧 {critical_quality} critical quality issues")

            # Build message
            message_parts = [f"## Deep Scan Results: {file_path}\n"]

            if include_security:
                sec = results["security"]["summary"]
                message_parts.append("### Security Analysis")
                message_parts.append(f"- Total vulnerabilities: {sec['total']}")
                message_parts.append(f"- Critical: {sec['critical_count']}")
                message_parts.append(f"- High: {sec['high_count']}")
                if results["security"]["vulnerabilities"]:
                    message_parts.append("\n**Vulnerabilities Found:**")
                    for v in results["security"]["vulnerabilities"][:5]:
                        message_parts.append(
                            f"  - [{v['severity'].upper()}] {v['type']}: {v['description']} (line {v['line_number']})"
                        )
                    if len(results["security"]["vulnerabilities"]) > 5:
                        message_parts.append(f"  ... and {len(results['security']['vulnerabilities']) - 5} more")
                message_parts.append("")

            if include_quality:
                met = results["quality"]["metrics"]
                message_parts.append("### Quality Analysis")
                message_parts.append(f"- Lines of code: {met['code_lines']}")
                message_parts.append(f"- Functions: {len(met['functions'])}")
                message_parts.append(f"- Classes: {met['classes']}")
                message_parts.append(f"- Average complexity: {met['average_complexity']}")
                message_parts.append(f"- Maintainability index: {met['maintainability_index']}")
                message_parts.append(f"- Quality rating: **{met['quality_rating']}**")
                if results["quality"]["issues"]:
                    message_parts.append("\n**Quality Issues:**")
                    for i in results["quality"]["issues"][:5]:
                        func = f" in {i['function_name']}" if i["function_name"] else ""
                        message_parts.append(f"  - [{i['severity'].upper()}] {i['type']}{func}: {i['description']}")
                    if len(results["quality"]["issues"]) > 5:
                        message_parts.append(f"  ... and {len(results['quality']['issues']) - 5} more")
                message_parts.append("")

            if issues_summary:
                message_parts.insert(1, "### Summary")
                for issue in issues_summary:
                    message_parts.insert(2, f"- {issue}")
                message_parts.insert(2 + len(issues_summary), "")

            return ToolResult(
                success=True,
                message="\n".join(message_parts),
                data=results,
            )

        except Exception as e:
            logger.error(f"Deep scan failed: {e}")
            return ToolResult(
                success=False,
                message=f"Deep scan failed: {e!s}",
            )

    @tool(
        name="deep_scan_security",
        description="Perform security vulnerability scan on source code. Detects SQL injection, XSS, hardcoded secrets, insecure functions, path traversal, and more.",
        parameters={
            "code": {"type": "string", "description": "Source code to analyze"},
            "file_path": {"type": "string", "description": "Path to the file (for reporting)"},
            "language": {"type": "string", "description": "Programming language", "enum": ["python", "javascript"]},
        },
        required=["code", "file_path", "language"],
    )
    async def deep_scan_security(
        self,
        code: str,
        file_path: str,
        language: str,
    ) -> ToolResult:
        """
        Perform security-focused code analysis.

        Args:
            code: Source code to analyze
            file_path: Path to the file
            language: Programming language

        Returns:
            Security analysis results
        """
        try:
            vulnerabilities = self._security_analyzer.analyze(code, file_path, language)
            summary = self._security_analyzer.get_summary(vulnerabilities)

            message_parts = [f"## Security Scan: {file_path}\n"]
            message_parts.append(f"**Total vulnerabilities found:** {summary['total']}")
            message_parts.append(f"- Critical: {summary['critical_count']}")
            message_parts.append(f"- High: {summary['high_count']}")
            message_parts.append(f"- Medium: {summary['by_severity'].get('medium', 0)}")
            message_parts.append(f"- Low: {summary['by_severity'].get('low', 0)}")
            message_parts.append("")

            if vulnerabilities:
                message_parts.append("### Vulnerabilities\n")
                for v in vulnerabilities:
                    message_parts.append(f"**[{v.severity.upper()}] {v.type}** (line {v.line_number})")
                    message_parts.append(f"  {v.description}")
                    message_parts.append(
                        f"  Code: `{v.code_snippet[:100]}...`"
                        if len(v.code_snippet) > 100
                        else f"  Code: `{v.code_snippet}`"
                    )
                    if v.recommendation:
                        message_parts.append(f"  Recommendation: {v.recommendation}")
                    if v.cwe_id:
                        message_parts.append(f"  CWE: {v.cwe_id}")
                    message_parts.append("")
            else:
                message_parts.append("✅ No security vulnerabilities detected.")

            return ToolResult(
                success=True,
                message="\n".join(message_parts),
                data={
                    "vulnerabilities": [v.to_dict() for v in vulnerabilities],
                    "summary": summary,
                },
            )

        except Exception as e:
            logger.error(f"Security scan failed: {e}")
            return ToolResult(
                success=False,
                message=f"Security scan failed: {e!s}",
            )

    @tool(
        name="deep_scan_quality",
        description="Analyze code quality metrics including cyclomatic complexity, maintainability index, function length, nesting depth, and code duplication.",
        parameters={
            "code": {"type": "string", "description": "Source code to analyze"},
            "file_path": {"type": "string", "description": "Path to the file"},
            "language": {"type": "string", "description": "Programming language", "enum": ["python", "javascript"]},
        },
        required=["code", "file_path", "language"],
    )
    async def deep_scan_quality(
        self,
        code: str,
        file_path: str,
        language: str,
    ) -> ToolResult:
        """
        Perform code quality analysis.

        Args:
            code: Source code to analyze
            file_path: Path to the file
            language: Programming language

        Returns:
            Quality analysis results
        """
        try:
            metrics, issues = self._quality_analyzer.analyze(code, file_path, language)

            message_parts = [f"## Quality Analysis: {file_path}\n"]
            message_parts.append("### Metrics")
            message_parts.append(f"- Total lines: {metrics.total_lines}")
            message_parts.append(f"- Code lines: {metrics.code_lines}")
            message_parts.append(f"- Comment lines: {metrics.comment_lines}")
            message_parts.append(f"- Blank lines: {metrics.blank_lines}")
            message_parts.append(f"- Comment ratio: {metrics.to_dict()['comment_ratio']}%")
            message_parts.append("")
            message_parts.append("### Structure")
            message_parts.append(f"- Functions: {len(metrics.functions)}")
            message_parts.append(f"- Classes: {metrics.classes}")
            message_parts.append(f"- Imports: {metrics.imports}")
            message_parts.append("")
            message_parts.append("### Complexity")
            message_parts.append(f"- Average cyclomatic complexity: {metrics.average_complexity:.2f}")
            message_parts.append(f"- Max complexity: {metrics.max_complexity}")
            message_parts.append(f"- Maintainability index: {metrics.maintainability_index:.2f}")
            message_parts.append(f"- Duplication ratio: {metrics.duplication_ratio:.2%}")
            message_parts.append("")
            message_parts.append(f"### Quality Rating: **{metrics.quality_rating.value.upper()}**")
            message_parts.append("")

            if metrics.functions:
                message_parts.append("### Function Metrics")
                for f in metrics.functions[:10]:
                    message_parts.append(
                        f"- `{f.name}`: complexity={f.cyclomatic_complexity}, "
                        f"lines={f.lines_of_code}, params={f.parameters}, "
                        f"nesting={f.nesting_depth}"
                    )
                if len(metrics.functions) > 10:
                    message_parts.append(f"... and {len(metrics.functions) - 10} more")
                message_parts.append("")

            if issues:
                message_parts.append("### Issues Found")
                for issue in issues:
                    func = f" in `{issue.function_name}`" if issue.function_name else ""
                    message_parts.append(f"- [{issue.severity.upper()}] {issue.type}{func}: {issue.description}")
                    message_parts.append(f"  → {issue.recommendation}")
            else:
                message_parts.append("✅ No quality issues detected.")

            return ToolResult(
                success=True,
                message="\n".join(message_parts),
                data={
                    "metrics": metrics.to_dict(),
                    "issues": [i.to_dict() for i in issues],
                },
            )

        except Exception as e:
            logger.error(f"Quality analysis failed: {e}")
            return ToolResult(
                success=False,
                message=f"Quality analysis failed: {e!s}",
            )

    @tool(
        name="deep_scan_dependencies",
        description="Analyze project dependencies for security vulnerabilities (CVEs), outdated packages, and unpinned versions. Supports requirements.txt (Python) and package.json (Node.js).",
        parameters={
            "content": {"type": "string", "description": "Content of the dependency file"},
            "file_type": {
                "type": "string",
                "description": "Type of dependency file",
                "enum": ["requirements.txt", "package.json"],
            },
            "file_path": {"type": "string", "description": "Path to the file (for reporting)"},
        },
        required=["content", "file_type"],
    )
    async def deep_scan_dependencies(
        self,
        content: str,
        file_type: str,
        file_path: str | None = None,
    ) -> ToolResult:
        """
        Analyze dependencies for vulnerabilities and issues.

        Args:
            content: Content of the dependency file
            file_type: Type of dependency file
            file_path: Optional file path for reporting

        Returns:
            Dependency analysis results
        """
        try:
            file_path = file_path or file_type

            if file_type == "requirements.txt":
                dependencies, issues = self._dependency_analyzer.analyze_requirements_txt(content, file_path)
            elif file_type == "package.json":
                dependencies, issues = self._dependency_analyzer.analyze_package_json(content, file_path)
            else:
                return ToolResult(
                    success=False,
                    message=f"Unsupported file type: {file_type}",
                )

            summary = self._dependency_analyzer.get_summary(dependencies, issues)

            message_parts = [f"## Dependency Analysis: {file_path}\n"]
            message_parts.append("### Overview")
            message_parts.append(f"- Total dependencies: {summary['total_dependencies']}")
            message_parts.append(f"- Production dependencies: {summary['production_dependencies']}")
            message_parts.append(f"- Dev dependencies: {summary['dev_dependencies']}")
            message_parts.append("")

            message_parts.append(f"### Issues Found: {summary['total_issues']}")
            message_parts.append(f"- Vulnerabilities: {summary['vulnerabilities']}")
            message_parts.append(f"- Outdated: {summary['outdated']}")
            message_parts.append(f"- Unpinned: {summary['unpinned']}")
            message_parts.append("")

            if summary["severity_breakdown"]:
                message_parts.append("### Severity Breakdown")
                for severity, count in summary["severity_breakdown"].items():
                    message_parts.append(f"- {severity.upper()}: {count}")
                message_parts.append("")

            # Show vulnerable dependencies
            vuln_issues = [i for i in issues if i.issue_type == "vulnerable"]
            if vuln_issues:
                message_parts.append("### 🚨 Vulnerable Dependencies")
                for issue in vuln_issues:
                    v = issue.vulnerability
                    message_parts.append(f"**{issue.dependency.name}** ({issue.dependency.version})")
                    message_parts.append(f"  - {v.cve_id}: {v.title}")
                    message_parts.append(f"  - Severity: {v.severity.value.upper()}")
                    message_parts.append(f"  - Affected: {v.affected_versions}")
                    message_parts.append(f"  - Fix: Upgrade to {v.fixed_version}")
                    message_parts.append("")

            # Show unpinned dependencies
            unpinned_issues = [i for i in issues if i.issue_type == "unpinned"]
            if unpinned_issues:
                message_parts.append("### ⚠️ Unpinned Dependencies")
                for issue in unpinned_issues:
                    message_parts.append(f"- `{issue.dependency.name}`: {issue.recommendation}")
                message_parts.append("")

            if not issues:
                message_parts.append("✅ No dependency issues detected.")

            return ToolResult(
                success=True,
                message="\n".join(message_parts),
                data={
                    "dependencies": [d.to_dict() for d in dependencies],
                    "issues": [i.to_dict() for i in issues],
                    "summary": summary,
                },
            )

        except Exception as e:
            logger.error(f"Dependency analysis failed: {e}")
            return ToolResult(
                success=False,
                message=f"Dependency analysis failed: {e!s}",
            )

    @tool(
        name="deep_scan_project",
        description="Scan multiple files in a project for comprehensive analysis. Provide a list of files with their content, paths, and types for batch analysis.",
        parameters={
            "files": {
                "type": "array",
                "description": "List of files to analyze",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "File content"},
                        "path": {"type": "string", "description": "File path"},
                        "language": {
                            "type": "string",
                            "description": "Language or file type",
                            "enum": ["python", "javascript", "requirements.txt", "package.json"],
                        },
                    },
                    "required": ["content", "path", "language"],
                },
            },
        },
        required=["files"],
    )
    async def deep_scan_project(
        self,
        files: list[dict[str, str]],
    ) -> ToolResult:
        """
        Perform comprehensive project-wide analysis.

        Args:
            files: List of files with content, path, and language

        Returns:
            Combined project analysis results
        """
        try:
            project_results = {
                "files_analyzed": 0,
                "total_security_issues": 0,
                "total_quality_issues": 0,
                "total_dependency_issues": 0,
                "file_results": [],
            }

            all_vulnerabilities = []
            all_quality_issues = []
            all_dependency_issues = []
            all_metrics = []

            for file_info in files:
                content = file_info["content"]
                path = file_info["path"]
                language = file_info["language"]

                file_result = {"path": path, "language": language}
                project_results["files_analyzed"] += 1

                # Handle dependency files
                if language in ["requirements.txt", "package.json"]:
                    if language == "requirements.txt":
                        _deps, dep_issues = self._dependency_analyzer.analyze_requirements_txt(content, path)
                    else:
                        _deps, dep_issues = self._dependency_analyzer.analyze_package_json(content, path)

                    all_dependency_issues.extend(dep_issues)
                    project_results["total_dependency_issues"] += len(dep_issues)
                    file_result["dependency_issues"] = len(dep_issues)

                # Handle source code files
                elif language in ["python", "javascript"]:
                    # Security scan
                    vulns = self._security_analyzer.analyze(content, path, language)
                    all_vulnerabilities.extend(vulns)
                    project_results["total_security_issues"] += len(vulns)
                    file_result["security_issues"] = len(vulns)

                    # Quality analysis
                    metrics, q_issues = self._quality_analyzer.analyze(content, path, language)
                    all_quality_issues.extend(q_issues)
                    all_metrics.append(metrics)
                    project_results["total_quality_issues"] += len(q_issues)
                    file_result["quality_issues"] = len(q_issues)
                    file_result["quality_rating"] = metrics.quality_rating.value

                project_results["file_results"].append(file_result)

            # Generate summaries
            security_summary = self._security_analyzer.get_summary(all_vulnerabilities)
            quality_summary = self._quality_analyzer.get_summary(all_metrics) if all_metrics else {"files": 0}

            project_results["security_summary"] = security_summary
            project_results["quality_summary"] = quality_summary

            # Build message
            message_parts = ["## Project Analysis Summary\n"]
            message_parts.append(f"**Files analyzed:** {project_results['files_analyzed']}")
            message_parts.append("")

            # Security summary
            message_parts.append("### Security")
            message_parts.append(f"- Total issues: {project_results['total_security_issues']}")
            message_parts.append(f"- Critical: {security_summary.get('critical_count', 0)}")
            message_parts.append(f"- High: {security_summary.get('high_count', 0)}")
            message_parts.append("")

            # Quality summary
            if quality_summary.get("files_analyzed", 0) > 0:
                message_parts.append("### Quality")
                message_parts.append(f"- Total issues: {project_results['total_quality_issues']}")
                message_parts.append(f"- Total lines of code: {quality_summary.get('total_lines_of_code', 0)}")
                message_parts.append(
                    f"- Average maintainability: {quality_summary.get('average_maintainability', 'N/A')}"
                )
                if quality_summary.get("quality_distribution"):
                    message_parts.append("- Quality distribution:")
                    for rating, count in quality_summary["quality_distribution"].items():
                        if count > 0:
                            message_parts.append(f"  - {rating}: {count} files")
                message_parts.append("")

            # Dependency summary
            if all_dependency_issues:
                message_parts.append("### Dependencies")
                message_parts.append(f"- Total issues: {project_results['total_dependency_issues']}")
                vuln_count = sum(1 for i in all_dependency_issues if i.issue_type == "vulnerable")
                message_parts.append(f"- Vulnerable packages: {vuln_count}")
                message_parts.append("")

            # Per-file breakdown
            message_parts.append("### File Results")
            for fr in project_results["file_results"]:
                issues = []
                if fr.get("security_issues", 0) > 0:
                    issues.append(f"🔒 {fr['security_issues']} security")
                if fr.get("quality_issues", 0) > 0:
                    issues.append(f"📊 {fr['quality_issues']} quality")
                if fr.get("dependency_issues", 0) > 0:
                    issues.append(f"📦 {fr['dependency_issues']} dependency")

                status = "✅" if not issues else "⚠️"
                rating = f" [{fr['quality_rating']}]" if fr.get("quality_rating") else ""
                issues_str = f" ({', '.join(issues)})" if issues else ""
                message_parts.append(f"- {status} `{fr['path']}`{rating}{issues_str}")

            return ToolResult(
                success=True,
                message="\n".join(message_parts),
                data=project_results,
            )

        except Exception as e:
            logger.error(f"Project analysis failed: {e}")
            return ToolResult(
                success=False,
                message=f"Project analysis failed: {e!s}",
            )
