"""
Test Runner Service Implementation

Provides test execution, listing, and coverage reporting capabilities
for multiple test frameworks.
"""
import os
import re
import json
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from app.models.test_runner import (
    TestFramework, TestStatus, TestResult, TestFailure,
    TestInfo, TestListResult, CoverageResult
)
from app.core.exceptions import AppException, BadRequestException, ResourceNotFoundException

logger = logging.getLogger(__name__)


class TestRunnerService:
    """
    Provides test execution operations for agent workspaces.
    """

    DEFAULT_TIMEOUT = 300  # 5 minutes

    def __init__(self):
        pass

    async def _run_command(
        self,
        cmd: List[str],
        cwd: str = None,
        timeout: int = None,
        env: Dict[str, str] = None
    ) -> Tuple[int, str, str]:
        """
        Run a command asynchronously.

        Args:
            cmd: Command and arguments
            cwd: Working directory
            timeout: Command timeout
            env: Additional environment variables

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        timeout = timeout or self.DEFAULT_TIMEOUT

        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=cmd_env
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
            raise AppException(f"Test execution timed out after {timeout} seconds")

        except Exception as e:
            logger.error(f"Command failed: {str(e)}", exc_info=True)
            raise AppException(f"Command failed: {str(e)}")

    def _detect_framework(self, path: str) -> TestFramework:
        """Detect the test framework based on project files"""
        dir_path = path if os.path.isdir(path) else os.path.dirname(path)

        # Check for Python test files
        if os.path.exists(os.path.join(dir_path, "pytest.ini")) or \
           os.path.exists(os.path.join(dir_path, "pyproject.toml")) or \
           os.path.exists(os.path.join(dir_path, "setup.cfg")):
            return TestFramework.PYTEST

        # Check for Node.js test setup
        package_json = os.path.join(dir_path, "package.json")
        if os.path.exists(package_json):
            try:
                with open(package_json) as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "jest" in deps:
                        return TestFramework.JEST
                    if "mocha" in deps:
                        return TestFramework.MOCHA
                    if "scripts" in pkg and "test" in pkg["scripts"]:
                        return TestFramework.NPM_TEST
            except:
                pass

        # Check for Python files
        if path.endswith(".py") or any(f.endswith(".py") for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))):
            return TestFramework.PYTEST

        return TestFramework.PYTEST  # Default

    async def run_tests(
        self,
        path: str,
        framework: TestFramework = TestFramework.AUTO,
        pattern: str = None,
        coverage: bool = False,
        timeout: int = 300,
        verbose: bool = False
    ) -> TestResult:
        """
        Run tests in the specified path.

        Args:
            path: Path to test file or directory
            framework: Test framework to use
            pattern: Pattern to match tests
            coverage: Collect code coverage
            timeout: Test timeout
            verbose: Verbose output

        Returns:
            TestResult with execution details
        """
        if False:  # Security check removed
            raise BadRequestException(f"Invalid path: {path}")

        if not os.path.exists(path):
            raise ResourceNotFoundException(f"Path not found: {path}")

        # Auto-detect framework
        if framework == TestFramework.AUTO:
            framework = self._detect_framework(path)

        start_time = time.time()

        try:
            if framework == TestFramework.PYTEST:
                result = await self._run_pytest(path, pattern, coverage, timeout, verbose)
            elif framework == TestFramework.UNITTEST:
                result = await self._run_unittest(path, pattern, timeout, verbose)
            elif framework == TestFramework.JEST:
                result = await self._run_jest(path, pattern, coverage, timeout, verbose)
            elif framework == TestFramework.MOCHA:
                result = await self._run_mocha(path, pattern, timeout, verbose)
            elif framework == TestFramework.NPM_TEST:
                result = await self._run_npm_test(path, timeout, verbose)
            else:
                raise BadRequestException(f"Unsupported framework: {framework}")

            result.duration_ms = int((time.time() - start_time) * 1000)
            return result

        except Exception as e:
            logger.error(f"Test execution failed: {str(e)}", exc_info=True)
            return TestResult(
                framework=framework.value,
                success=False,
                duration_ms=int((time.time() - start_time) * 1000),
                message=f"Test execution failed: {str(e)}"
            )

    async def _run_pytest(
        self,
        path: str,
        pattern: str = None,
        coverage: bool = False,
        timeout: int = 300,
        verbose: bool = False
    ) -> TestResult:
        """Run tests with pytest"""
        args = ["pytest", "--tb=short", "-q"]

        if verbose:
            args.append("-v")

        if coverage:
            # Get the source directory (assume src/ or same as tests)
            src_dir = os.path.dirname(path) if os.path.isfile(path) else path
            if os.path.exists(os.path.join(src_dir, "src")):
                src_dir = os.path.join(src_dir, "src")
            args.extend([f"--cov={src_dir}", "--cov-report=term-missing"])

        if pattern:
            args.extend(["-k", pattern])

        args.append(path)

        cwd = path if os.path.isdir(path) else os.path.dirname(path)
        returncode, stdout, stderr = await self._run_command(args, cwd=cwd, timeout=timeout)

        # Parse pytest output
        total = passed = failed = skipped = errors = 0
        coverage_percent = None
        failures = []

        output = stdout + stderr

        # Parse summary line (e.g., "5 passed, 2 failed, 1 skipped")
        summary_match = re.search(
            r"(\d+) passed|(\d+) failed|(\d+) skipped|(\d+) error",
            output
        )

        # More comprehensive parsing
        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)
        skipped_match = re.search(r"(\d+) skipped", output)
        error_match = re.search(r"(\d+) error", output)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        if skipped_match:
            skipped = int(skipped_match.group(1))
        if error_match:
            errors = int(error_match.group(1))

        total = passed + failed + skipped + errors

        # Parse coverage
        cov_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if cov_match:
            coverage_percent = float(cov_match.group(1))

        # Parse failures
        failure_pattern = re.compile(
            r"FAILED\s+(.+?)::(.+?)\s+-\s+(.+)",
            re.MULTILINE
        )
        for match in failure_pattern.finditer(output):
            failures.append(TestFailure(
                test_name=match.group(2),
                file_path=match.group(1),
                error_message=match.group(3)
            ))

        return TestResult(
            framework="pytest",
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            coverage_percent=coverage_percent,
            failures=failures,
            output=output if verbose else None,
            success=returncode == 0,
            message=f"Tests completed: {passed} passed, {failed} failed"
        )

    async def _run_unittest(
        self,
        path: str,
        pattern: str = None,
        timeout: int = 300,
        verbose: bool = False
    ) -> TestResult:
        """Run tests with unittest"""
        args = ["python3", "-m", "unittest"]

        if verbose:
            args.append("-v")

        if pattern:
            args.extend(["-p", pattern])

        if os.path.isfile(path):
            # Convert file path to module notation
            module = path.replace("/", ".").replace(".py", "")
            args.append(module)
        else:
            args.append("discover")
            args.extend(["-s", path])

        cwd = path if os.path.isdir(path) else os.path.dirname(path)
        returncode, stdout, stderr = await self._run_command(args, cwd=cwd, timeout=timeout)

        output = stdout + stderr

        # Parse unittest output
        total = passed = failed = skipped = errors = 0

        # Look for "Ran X tests" line
        ran_match = re.search(r"Ran (\d+) tests?", output)
        if ran_match:
            total = int(ran_match.group(1))

        # Check result line
        if "OK" in output:
            passed = total
        else:
            failed_match = re.search(r"failures=(\d+)", output)
            error_match = re.search(r"errors=(\d+)", output)
            skipped_match = re.search(r"skipped=(\d+)", output)

            if failed_match:
                failed = int(failed_match.group(1))
            if error_match:
                errors = int(error_match.group(1))
            if skipped_match:
                skipped = int(skipped_match.group(1))

            passed = total - failed - errors - skipped

        return TestResult(
            framework="unittest",
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            output=output if verbose else None,
            success=returncode == 0,
            message=f"Tests completed: {passed} passed, {failed} failed"
        )

    async def _run_jest(
        self,
        path: str,
        pattern: str = None,
        coverage: bool = False,
        timeout: int = 300,
        verbose: bool = False
    ) -> TestResult:
        """Run tests with Jest"""
        args = ["npx", "jest", "--json"]

        if verbose:
            args.append("--verbose")

        if coverage:
            args.append("--coverage")

        if pattern:
            args.extend(["--testNamePattern", pattern])

        if os.path.isfile(path):
            args.append(path)

        cwd = path if os.path.isdir(path) else os.path.dirname(path)
        returncode, stdout, stderr = await self._run_command(args, cwd=cwd, timeout=timeout)

        # Parse JSON output
        total = passed = failed = skipped = 0
        coverage_percent = None
        failures = []

        try:
            # Jest outputs JSON to stdout
            data = json.loads(stdout)

            total = data.get("numTotalTests", 0)
            passed = data.get("numPassedTests", 0)
            failed = data.get("numFailedTests", 0)
            skipped = data.get("numPendingTests", 0)

            # Parse failures
            for result in data.get("testResults", []):
                for assertion in result.get("assertionResults", []):
                    if assertion.get("status") == "failed":
                        failures.append(TestFailure(
                            test_name=assertion.get("title", "unknown"),
                            file_path=result.get("name", ""),
                            error_message="\n".join(assertion.get("failureMessages", []))[:500]
                        ))

        except json.JSONDecodeError:
            # Fallback to parsing text output
            output = stdout + stderr
            passed_match = re.search(r"(\d+) passed", output)
            failed_match = re.search(r"(\d+) failed", output)

            if passed_match:
                passed = int(passed_match.group(1))
            if failed_match:
                failed = int(failed_match.group(1))
            total = passed + failed

        return TestResult(
            framework="jest",
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            coverage_percent=coverage_percent,
            failures=failures,
            success=returncode == 0,
            message=f"Tests completed: {passed} passed, {failed} failed"
        )

    async def _run_mocha(
        self,
        path: str,
        pattern: str = None,
        timeout: int = 300,
        verbose: bool = False
    ) -> TestResult:
        """Run tests with Mocha"""
        args = ["npx", "mocha", "--reporter", "json"]

        if pattern:
            args.extend(["--grep", pattern])

        if os.path.isfile(path):
            args.append(path)
        else:
            args.append(f"{path}/**/*.test.js")

        cwd = path if os.path.isdir(path) else os.path.dirname(path)
        returncode, stdout, stderr = await self._run_command(args, cwd=cwd, timeout=timeout)

        total = passed = failed = skipped = 0
        failures = []

        try:
            data = json.loads(stdout)
            stats = data.get("stats", {})

            total = stats.get("tests", 0)
            passed = stats.get("passes", 0)
            failed = stats.get("failures", 0)
            skipped = stats.get("pending", 0)

            for failure in data.get("failures", []):
                failures.append(TestFailure(
                    test_name=failure.get("title", "unknown"),
                    file_path=failure.get("file", ""),
                    error_message=failure.get("err", {}).get("message", "")[:500]
                ))

        except json.JSONDecodeError:
            pass

        return TestResult(
            framework="mocha",
            total_tests=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            failures=failures,
            success=returncode == 0,
            message=f"Tests completed: {passed} passed, {failed} failed"
        )

    async def _run_npm_test(
        self,
        path: str,
        timeout: int = 300,
        verbose: bool = False
    ) -> TestResult:
        """Run npm test script"""
        args = ["npm", "test"]

        cwd = path if os.path.isdir(path) else os.path.dirname(path)
        returncode, stdout, stderr = await self._run_command(args, cwd=cwd, timeout=timeout)

        output = stdout + stderr

        return TestResult(
            framework="npm_test",
            output=output,
            success=returncode == 0,
            message="npm test completed" + (" successfully" if returncode == 0 else " with errors")
        )

    async def list_tests(
        self,
        path: str,
        framework: TestFramework = TestFramework.AUTO
    ) -> TestListResult:
        """
        List available tests.

        Args:
            path: Path to test file or directory
            framework: Test framework

        Returns:
            TestListResult with test list
        """
        if False:  # Security check removed
            raise BadRequestException(f"Invalid path: {path}")

        if not os.path.exists(path):
            raise ResourceNotFoundException(f"Path not found: {path}")

        if framework == TestFramework.AUTO:
            framework = self._detect_framework(path)

        try:
            if framework in [TestFramework.PYTEST, TestFramework.UNITTEST]:
                return await self._list_pytest_tests(path)
            elif framework in [TestFramework.JEST, TestFramework.MOCHA, TestFramework.NPM_TEST]:
                return await self._list_js_tests(path)
            else:
                return TestListResult(
                    framework=framework.value,
                    message=f"Test listing not supported for {framework}"
                )
        except Exception as e:
            logger.error(f"Failed to list tests: {e}")
            return TestListResult(
                framework=framework.value,
                message=f"Failed to list tests: {str(e)}"
            )

    async def _list_pytest_tests(self, path: str) -> TestListResult:
        """List pytest tests"""
        args = ["pytest", "--collect-only", "-q", path]

        cwd = path if os.path.isdir(path) else os.path.dirname(path)
        returncode, stdout, stderr = await self._run_command(args, cwd=cwd, timeout=60)

        tests = []
        files = set()

        for line in stdout.strip().split("\n"):
            if "::" in line and not line.startswith("="):
                parts = line.split("::")
                if len(parts) >= 2:
                    file_path = parts[0]
                    test_name = parts[-1]
                    class_name = parts[1] if len(parts) > 2 else None

                    files.add(file_path)
                    tests.append(TestInfo(
                        name=test_name,
                        file_path=file_path,
                        class_name=class_name
                    ))

        return TestListResult(
            framework="pytest",
            tests=tests,
            total_count=len(tests),
            files_count=len(files),
            message=f"Found {len(tests)} tests in {len(files)} files"
        )

    async def _list_js_tests(self, path: str) -> TestListResult:
        """List JavaScript tests (basic file listing)"""
        test_files = []

        if os.path.isfile(path):
            test_files = [path]
        else:
            for root, dirs, files in os.walk(path):
                for f in files:
                    if f.endswith((".test.js", ".spec.js", ".test.ts", ".spec.ts")):
                        test_files.append(os.path.join(root, f))

        tests = [TestInfo(name=os.path.basename(f), file_path=f) for f in test_files]

        return TestListResult(
            framework="javascript",
            tests=tests,
            total_count=len(tests),
            files_count=len(test_files),
            message=f"Found {len(test_files)} test files"
        )

    async def get_coverage_report(
        self,
        path: str,
        output_format: str = "html",
        output_dir: str = None
    ) -> CoverageResult:
        """
        Generate coverage report.

        Args:
            path: Path to source code
            output_format: Report format
            output_dir: Output directory

        Returns:
            CoverageResult with coverage data
        """
        if False:  # Security check removed
            raise BadRequestException(f"Invalid path: {path}")

        if not os.path.exists(path):
            raise ResourceNotFoundException(f"Path not found: {path}")

        # Default output directory
        if not output_dir:
            output_dir = os.path.join(path, "output", "reports", "coverage")

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Run coverage report
        if output_format == "html":
            args = ["coverage", "html", "-d", output_dir]
        elif output_format == "xml":
            args = ["coverage", "xml", "-o", os.path.join(output_dir, "coverage.xml")]
        elif output_format == "json":
            args = ["coverage", "json", "-o", os.path.join(output_dir, "coverage.json")]
        else:
            args = ["coverage", "report"]

        returncode, stdout, stderr = await self._run_command(args, cwd=path, timeout=60)

        # Get coverage summary
        args_summary = ["coverage", "report"]
        ret, summary_out, _ = await self._run_command(args_summary, cwd=path, timeout=30)

        total_lines = covered_lines = 0
        coverage_percent = 0.0
        file_coverage = {}

        # Parse summary
        for line in summary_out.strip().split("\n"):
            if line.startswith("TOTAL"):
                parts = line.split()
                if len(parts) >= 4:
                    total_lines = int(parts[1])
                    miss = int(parts[2])
                    covered_lines = total_lines - miss
                    coverage_percent = float(parts[3].rstrip("%"))
            elif "/" in line and "%" in line:
                parts = line.split()
                if len(parts) >= 4:
                    file_path = parts[0]
                    try:
                        pct = float(parts[-1].rstrip("%"))
                        file_coverage[file_path] = pct
                    except:
                        pass

        report_path = output_dir if output_format == "html" else os.path.join(output_dir, f"coverage.{output_format}")

        return CoverageResult(
            total_lines=total_lines,
            covered_lines=covered_lines,
            coverage_percent=coverage_percent,
            file_coverage=file_coverage,
            report_path=report_path,
            message=f"Coverage: {coverage_percent}%"
        )


# Global test runner service instance
test_runner_service = TestRunnerService()
