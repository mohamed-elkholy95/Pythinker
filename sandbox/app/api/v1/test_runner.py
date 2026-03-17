"""
Test Runner API Endpoints

Provides REST API for test execution, listing, and coverage reporting.
"""

from fastapi import APIRouter
from app.schemas.test_runner import (
    TestRunRequest,
    TestListRequest,
    CoverageReportRequest,
)
from app.schemas.response import Response
from app.services.test_runner import test_runner_service
from app.core.exceptions import BadRequestException

router = APIRouter()


@router.post("/run", response_model=Response)
async def run_tests(request: TestRunRequest):
    """
    Run tests in the specified path.

    Auto-detects framework: pytest, unittest (Python), jest, mocha (JavaScript).
    Supports coverage collection and pattern matching.
    """
    if not request.path:
        raise BadRequestException("Path is required")

    result = await test_runner_service.run_tests(
        path=request.path,
        framework=request.framework,
        pattern=request.pattern,
        coverage=request.coverage,
        timeout=request.timeout,
        verbose=request.verbose,
    )

    return Response(
        success=result.success,
        message=result.message or "Test execution completed",
        data=result.model_dump(exclude={"message"}),
    )


@router.post("/list", response_model=Response)
async def list_tests(request: TestListRequest):
    """
    List available tests without executing them.

    Returns test names, file paths, and class names (if applicable).
    """
    if not request.path:
        raise BadRequestException("Path is required")

    result = await test_runner_service.list_tests(
        path=request.path, framework=request.framework
    )

    return Response(
        success=True,
        message=result.message or "Tests listed",
        data=result.model_dump(exclude={"message"}),
    )


@router.post("/coverage", response_model=Response)
async def get_coverage_report(request: CoverageReportRequest):
    """
    Generate code coverage report.

    Supports HTML, XML, and JSON output formats.
    """
    if not request.path:
        raise BadRequestException("Path is required")

    result = await test_runner_service.get_coverage_report(
        path=request.path,
        output_format=request.output_format,
        output_dir=request.output_dir,
    )

    return Response(
        success=True,
        message=result.message or "Coverage report generated",
        data=result.model_dump(exclude={"message"}),
    )
