"""
Code Development Service Implementation

Provides code formatting, linting, analysis, and search capabilities
for agent workspaces.
"""
import os
import re
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path

from app.models.code_dev import (
    Formatter, Linter, AnalysisType,
    FormatResult, LintResult, LintIssue,
    AnalysisResult, SecurityIssue,
    SearchResult, SearchMatch
)
from app.core.security import security_manager
from app.core.exceptions import AppException, BadRequestException, ResourceNotFoundException

logger = logging.getLogger(__name__)


class CodeDevService:
    """
    Provides code development operations for agent workspaces.
    """

    DEFAULT_TIMEOUT = 60

    # File extension to formatter mapping
    FORMATTER_MAP = {
        ".py": Formatter.BLACK,
        ".pyi": Formatter.BLACK,
        ".js": Formatter.PRETTIER,
        ".jsx": Formatter.PRETTIER,
        ".ts": Formatter.PRETTIER,
        ".tsx": Formatter.PRETTIER,
        ".json": Formatter.PRETTIER,
        ".css": Formatter.PRETTIER,
        ".scss": Formatter.PRETTIER,
        ".html": Formatter.PRETTIER,
        ".md": Formatter.PRETTIER,
        ".yaml": Formatter.PRETTIER,
        ".yml": Formatter.PRETTIER,
    }

    # File extension to linter mapping
    LINTER_MAP = {
        ".py": Linter.FLAKE8,
        ".pyi": Linter.FLAKE8,
        ".js": Linter.ESLINT,
        ".jsx": Linter.ESLINT,
        ".ts": Linter.ESLINT,
        ".tsx": Linter.ESLINT,
    }

    def __init__(self):
        pass

    async def _run_command(
        self,
        cmd: List[str],
        cwd: str = None,
        timeout: int = None
    ) -> tuple[int, str, str]:
        """
        Run a command asynchronously.

        Args:
            cmd: Command and arguments
            cwd: Working directory
            timeout: Command timeout

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        timeout = timeout or self.DEFAULT_TIMEOUT

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return (
                process.returncode,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace")
            )

        except asyncio.TimeoutError:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            try:
                process.kill()
            except:
                pass
            raise AppException(f"Command timed out after {timeout} seconds")

        except Exception as e:
            logger.error(f"Command failed: {str(e)}", exc_info=True)
            raise AppException(f"Command failed: {str(e)}")

    def _detect_formatter(self, file_path: str) -> Formatter:
        """Detect appropriate formatter for file type"""
        ext = Path(file_path).suffix.lower()
        return self.FORMATTER_MAP.get(ext, Formatter.PRETTIER)

    def _detect_linter(self, path: str) -> Linter:
        """Detect appropriate linter for file type"""
        if os.path.isfile(path):
            ext = Path(path).suffix.lower()
            return self.LINTER_MAP.get(ext, Linter.FLAKE8)

        # For directories, check for common files
        if os.path.exists(os.path.join(path, "package.json")):
            return Linter.ESLINT
        if os.path.exists(os.path.join(path, "requirements.txt")) or \
           os.path.exists(os.path.join(path, "setup.py")):
            return Linter.FLAKE8

        return Linter.FLAKE8

    async def format_code(
        self,
        file_path: str,
        formatter: Formatter = Formatter.AUTO,
        check_only: bool = False
    ) -> FormatResult:
        """
        Format a code file.

        Args:
            file_path: Path to file to format
            formatter: Formatter to use
            check_only: Check without modifying

        Returns:
            FormatResult with formatting details
        """
        if not security_manager.validate_path(file_path):
            raise BadRequestException(f"Invalid file path: {file_path}")

        if not os.path.exists(file_path):
            raise ResourceNotFoundException(f"File not found: {file_path}")

        if not os.path.isfile(file_path):
            raise BadRequestException(f"Path is not a file: {file_path}")

        # Auto-detect formatter
        if formatter == Formatter.AUTO:
            formatter = self._detect_formatter(file_path)

        try:
            if formatter == Formatter.BLACK:
                return await self._format_black(file_path, check_only)
            elif formatter == Formatter.ISORT:
                return await self._format_isort(file_path, check_only)
            elif formatter == Formatter.AUTOPEP8:
                return await self._format_autopep8(file_path, check_only)
            elif formatter == Formatter.PRETTIER:
                return await self._format_prettier(file_path, check_only)
            else:
                raise BadRequestException(f"Unsupported formatter: {formatter}")

        except Exception as e:
            logger.error(f"Formatting failed: {str(e)}", exc_info=True)
            return FormatResult(
                success=False,
                file_path=file_path,
                formatter=formatter.value,
                changed=False,
                message=f"Formatting failed: {str(e)}"
            )

    async def _format_black(self, file_path: str, check_only: bool) -> FormatResult:
        """Format with black"""
        args = ["black"]
        if check_only:
            args.extend(["--check", "--diff"])
        args.append(file_path)

        returncode, stdout, stderr = await self._run_command(args)

        changed = returncode == 1 if check_only else "reformatted" in stderr.lower()

        return FormatResult(
            success=returncode == 0 or (check_only and returncode == 1),
            file_path=file_path,
            formatter="black",
            changed=changed,
            diff=stdout if check_only and changed else None,
            message="File formatted" if not check_only else ("Would reformat" if changed else "File already formatted")
        )

    async def _format_isort(self, file_path: str, check_only: bool) -> FormatResult:
        """Format imports with isort"""
        args = ["isort"]
        if check_only:
            args.extend(["--check-only", "--diff"])
        args.append(file_path)

        returncode, stdout, stderr = await self._run_command(args)

        return FormatResult(
            success=returncode == 0,
            file_path=file_path,
            formatter="isort",
            changed=returncode == 1 if check_only else bool(stdout),
            diff=stdout if check_only else None,
            message="Imports sorted"
        )

    async def _format_autopep8(self, file_path: str, check_only: bool) -> FormatResult:
        """Format with autopep8"""
        args = ["autopep8"]
        if check_only:
            args.append("--diff")
        else:
            args.append("--in-place")
        args.append(file_path)

        returncode, stdout, stderr = await self._run_command(args)

        return FormatResult(
            success=returncode == 0,
            file_path=file_path,
            formatter="autopep8",
            changed=bool(stdout) if check_only else True,
            diff=stdout if check_only else None,
            message="File formatted with autopep8"
        )

    async def _format_prettier(self, file_path: str, check_only: bool) -> FormatResult:
        """Format with prettier"""
        args = ["prettier"]
        if check_only:
            args.append("--check")
        else:
            args.append("--write")
        args.append(file_path)

        returncode, stdout, stderr = await self._run_command(args)

        changed = returncode == 1 if check_only else "modified" in stdout.lower() or returncode == 0

        return FormatResult(
            success=returncode == 0 or (check_only and returncode == 1),
            file_path=file_path,
            formatter="prettier",
            changed=changed,
            message="File formatted" if not check_only else ("Would reformat" if changed else "File already formatted")
        )

    async def lint_code(
        self,
        path: str,
        linter: Linter = Linter.AUTO,
        fix: bool = False
    ) -> LintResult:
        """
        Lint code files.

        Args:
            path: Path to file or directory
            linter: Linter to use
            fix: Auto-fix issues where possible

        Returns:
            LintResult with linting details
        """
        if not security_manager.validate_path(path):
            raise BadRequestException(f"Invalid path: {path}")

        if not os.path.exists(path):
            raise ResourceNotFoundException(f"Path not found: {path}")

        # Auto-detect linter
        if linter == Linter.AUTO:
            linter = self._detect_linter(path)

        try:
            if linter == Linter.FLAKE8:
                return await self._lint_flake8(path)
            elif linter == Linter.PYLINT:
                return await self._lint_pylint(path)
            elif linter == Linter.MYPY:
                return await self._lint_mypy(path)
            elif linter == Linter.ESLINT:
                return await self._lint_eslint(path, fix)
            else:
                raise BadRequestException(f"Unsupported linter: {linter}")

        except Exception as e:
            logger.error(f"Linting failed: {str(e)}", exc_info=True)
            return LintResult(
                success=False,
                path=path,
                linter=linter.value,
                message=f"Linting failed: {str(e)}"
            )

    async def _lint_flake8(self, path: str) -> LintResult:
        """Lint with flake8"""
        args = ["flake8", "--format=json", path]

        returncode, stdout, stderr = await self._run_command(args)

        issues = []
        if stdout.strip():
            # flake8 outputs one issue per line in default format
            # Using a simpler parsing approach
            for line in stdout.strip().split("\n"):
                if not line:
                    continue
                # Format: file:line:col: code message
                match = re.match(r"(.+):(\d+):(\d+):\s*(\w+)\s*(.*)", line)
                if match:
                    issues.append(LintIssue(
                        file=match.group(1),
                        line=int(match.group(2)),
                        column=int(match.group(3)),
                        code=match.group(4),
                        message=match.group(5),
                        severity="error" if match.group(4).startswith("E") else "warning"
                    ))

        errors = sum(1 for i in issues if i.severity == "error")
        warnings = len(issues) - errors

        return LintResult(
            success=returncode == 0,
            path=path,
            linter="flake8",
            issues=issues,
            issues_count=len(issues),
            errors_count=errors,
            warnings_count=warnings,
            message=f"Found {len(issues)} issues" if issues else "No issues found"
        )

    async def _lint_pylint(self, path: str) -> LintResult:
        """Lint with pylint"""
        args = ["pylint", "--output-format=json", path]

        returncode, stdout, stderr = await self._run_command(args, timeout=120)

        issues = []
        if stdout.strip():
            try:
                data = json.loads(stdout)
                for item in data:
                    issues.append(LintIssue(
                        file=item.get("path", ""),
                        line=item.get("line", 0),
                        column=item.get("column", 0),
                        code=item.get("message-id", ""),
                        message=item.get("message", ""),
                        severity="error" if item.get("type") == "error" else "warning"
                    ))
            except json.JSONDecodeError:
                pass

        errors = sum(1 for i in issues if i.severity == "error")

        return LintResult(
            success=True,  # pylint returns non-zero for any issues
            path=path,
            linter="pylint",
            issues=issues,
            issues_count=len(issues),
            errors_count=errors,
            warnings_count=len(issues) - errors,
            message=f"Found {len(issues)} issues"
        )

    async def _lint_mypy(self, path: str) -> LintResult:
        """Type check with mypy"""
        args = ["mypy", "--no-error-summary", path]

        returncode, stdout, stderr = await self._run_command(args, timeout=120)

        issues = []
        for line in stdout.strip().split("\n"):
            if not line:
                continue
            # Format: file:line: severity: message
            match = re.match(r"(.+):(\d+):\s*(\w+):\s*(.*)", line)
            if match:
                severity_str = match.group(3).lower()
                issues.append(LintIssue(
                    file=match.group(1),
                    line=int(match.group(2)),
                    column=0,
                    code="",
                    message=match.group(4),
                    severity="error" if severity_str == "error" else "warning"
                ))

        errors = sum(1 for i in issues if i.severity == "error")

        return LintResult(
            success=returncode == 0,
            path=path,
            linter="mypy",
            issues=issues,
            issues_count=len(issues),
            errors_count=errors,
            warnings_count=len(issues) - errors,
            message=f"Found {len(issues)} type issues"
        )

    async def _lint_eslint(self, path: str, fix: bool = False) -> LintResult:
        """Lint with eslint"""
        args = ["eslint", "--format=json"]
        if fix:
            args.append("--fix")
        args.append(path)

        returncode, stdout, stderr = await self._run_command(args)

        issues = []
        fixed_count = 0

        if stdout.strip():
            try:
                data = json.loads(stdout)
                for file_result in data:
                    for msg in file_result.get("messages", []):
                        issues.append(LintIssue(
                            file=file_result.get("filePath", ""),
                            line=msg.get("line", 0),
                            column=msg.get("column", 0),
                            code=msg.get("ruleId", ""),
                            message=msg.get("message", ""),
                            severity="error" if msg.get("severity") == 2 else "warning"
                        ))
                    if fix:
                        fixed_count += file_result.get("fixableErrorCount", 0)
                        fixed_count += file_result.get("fixableWarningCount", 0)
            except json.JSONDecodeError:
                pass

        errors = sum(1 for i in issues if i.severity == "error")

        return LintResult(
            success=len(issues) == 0,
            path=path,
            linter="eslint",
            issues=issues,
            issues_count=len(issues),
            errors_count=errors,
            warnings_count=len(issues) - errors,
            fixed_count=fixed_count,
            message=f"Found {len(issues)} issues" + (f", fixed {fixed_count}" if fix and fixed_count else "")
        )

    async def analyze_code(
        self,
        path: str,
        analysis_type: AnalysisType = AnalysisType.ALL
    ) -> AnalysisResult:
        """
        Analyze code for security issues and complexity.

        Args:
            path: Path to file or directory
            analysis_type: Type of analysis

        Returns:
            AnalysisResult with analysis details
        """
        if not security_manager.validate_path(path):
            raise BadRequestException(f"Invalid path: {path}")

        if not os.path.exists(path):
            raise ResourceNotFoundException(f"Path not found: {path}")

        security_issues = []
        security_score = None
        summary = {}

        # Run security analysis with bandit for Python files
        if analysis_type in [AnalysisType.SECURITY, AnalysisType.ALL]:
            try:
                security_issues, security_score = await self._analyze_security(path)
                summary["security"] = {
                    "issues_found": len(security_issues),
                    "score": security_score
                }
            except Exception as e:
                logger.warning(f"Security analysis failed: {e}")
                summary["security"] = {"error": str(e)}

        # Add complexity analysis placeholder
        if analysis_type in [AnalysisType.COMPLEXITY, AnalysisType.ALL]:
            summary["complexity"] = {
                "note": "Complexity analysis available via radon (not installed by default)"
            }

        return AnalysisResult(
            success=True,
            path=path,
            analysis_type=analysis_type.value,
            security_issues=security_issues,
            security_score=security_score,
            summary=summary,
            message=f"Analysis complete. Found {len(security_issues)} security issues."
        )

    async def _analyze_security(self, path: str) -> tuple[List[SecurityIssue], float]:
        """Run security analysis with bandit"""
        args = ["bandit", "-r", "-f", "json", path]

        returncode, stdout, stderr = await self._run_command(args, timeout=120)

        issues = []
        score = 100.0

        if stdout.strip():
            try:
                data = json.loads(stdout)
                results = data.get("results", [])

                for item in results:
                    issues.append(SecurityIssue(
                        file=item.get("filename", ""),
                        line=item.get("line_number", 0),
                        issue_id=item.get("test_id", ""),
                        severity=item.get("issue_severity", "medium").lower(),
                        confidence=item.get("issue_confidence", "medium").lower(),
                        issue_text=item.get("issue_text", ""),
                        cwe=item.get("cwe", {}).get("id") if item.get("cwe") else None
                    ))

                # Calculate score (simple deduction)
                high_issues = sum(1 for i in issues if i.severity == "high")
                medium_issues = sum(1 for i in issues if i.severity == "medium")
                low_issues = sum(1 for i in issues if i.severity == "low")

                score = max(0, 100 - (high_issues * 20) - (medium_issues * 10) - (low_issues * 5))

            except json.JSONDecodeError:
                pass

        return issues, score

    async def search_code(
        self,
        directory: str,
        pattern: str,
        file_glob: str = "*",
        context_lines: int = 2,
        max_results: int = 100
    ) -> SearchResult:
        """
        Search for pattern in code files.

        Args:
            directory: Directory to search
            pattern: Search pattern
            file_glob: Glob pattern to filter files
            context_lines: Context lines around match
            max_results: Maximum results

        Returns:
            SearchResult with matches
        """
        if not security_manager.validate_path(directory):
            raise BadRequestException(f"Invalid directory: {directory}")

        if not os.path.exists(directory):
            raise ResourceNotFoundException(f"Directory not found: {directory}")

        # Use ripgrep for fast searching
        args = [
            "rg",
            "--json",
            f"-C{context_lines}",
            f"--max-count={max_results}",
            f"--glob={file_glob}",
            pattern,
            directory
        ]

        returncode, stdout, stderr = await self._run_command(args, timeout=60)

        matches = []
        files_searched = set()
        current_match = None
        context_before = []
        context_after = []

        if stdout.strip():
            for line in stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    msg_type = data.get("type")

                    if msg_type == "match":
                        # Save previous match if exists
                        if current_match:
                            current_match.context_before = context_before
                            current_match.context_after = context_after
                            matches.append(current_match)

                        match_data = data.get("data", {})
                        file_path = match_data.get("path", {}).get("text", "")
                        files_searched.add(file_path)

                        current_match = SearchMatch(
                            file=file_path,
                            line=match_data.get("line_number", 0),
                            content=match_data.get("lines", {}).get("text", "").strip(),
                            context_before=[],
                            context_after=[]
                        )
                        context_before = []
                        context_after = []

                    elif msg_type == "context":
                        ctx_data = data.get("data", {})
                        ctx_line = ctx_data.get("lines", {}).get("text", "").strip()

                        if current_match is None:
                            context_before.append(ctx_line)
                        else:
                            context_after.append(ctx_line)

                    elif msg_type == "summary":
                        summary = data.get("data", {})
                        # Process summary if needed

                except json.JSONDecodeError:
                    continue

            # Add last match
            if current_match:
                current_match.context_before = context_before
                current_match.context_after = context_after
                matches.append(current_match)

        return SearchResult(
            success=True,
            pattern=pattern,
            directory=directory,
            matches=matches[:max_results],
            total_matches=len(matches),
            files_searched=len(files_searched),
            message=f"Found {len(matches)} matches in {len(files_searched)} files"
        )


# Global code dev service instance
code_dev_service = CodeDevService()
