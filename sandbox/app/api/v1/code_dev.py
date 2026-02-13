"""
Code Development API Endpoints

Provides REST API for code formatting, linting, analysis, and search.
"""

from fastapi import APIRouter
from app.schemas.code_dev import (
    CodeFormatRequest,
    CodeLintRequest,
    CodeAnalyzeRequest,
    CodeSearchRequest,
)
from app.schemas.response import Response
from app.services.code_dev import code_dev_service
from app.core.exceptions import BadRequestException

router = APIRouter()


@router.post("/format", response_model=Response)
async def format_code(request: CodeFormatRequest):
    """
    Format a code file.

    Supports: black (Python), prettier (JS/TS/JSON/CSS/HTML/MD).
    Auto-detects formatter from file extension.
    """
    if not request.file_path:
        raise BadRequestException("File path is required")

    result = await code_dev_service.format_code(
        file_path=request.file_path,
        formatter=request.formatter,
        check_only=request.check_only,
    )

    return Response(
        success=result.success,
        message=result.message or "Format operation completed",
        data=result.model_dump(exclude={"message"}),
    )


@router.post("/lint", response_model=Response)
async def lint_code(request: CodeLintRequest):
    """
    Lint code files.

    Supports: flake8, pylint, mypy (Python), eslint (JS/TS).
    Auto-detects linter from file type.
    """
    if not request.path:
        raise BadRequestException("Path is required")

    result = await code_dev_service.lint_code(
        path=request.path, linter=request.linter, fix=request.fix
    )

    return Response(
        success=result.success,
        message=result.message or "Lint operation completed",
        data=result.model_dump(exclude={"message"}),
    )


@router.post("/analyze", response_model=Response)
async def analyze_code(request: CodeAnalyzeRequest):
    """
    Analyze code for security issues and complexity.

    Uses bandit for Python security analysis.
    """
    if not request.path:
        raise BadRequestException("Path is required")

    result = await code_dev_service.analyze_code(
        path=request.path, analysis_type=request.analysis_type
    )

    return Response(
        success=result.success,
        message=result.message or "Analysis completed",
        data=result.model_dump(exclude={"message"}),
    )


@router.post("/search", response_model=Response)
async def search_code(request: CodeSearchRequest):
    """
    Search for pattern in code files.

    Uses ripgrep for fast, regex-enabled search.
    """
    if not request.directory:
        raise BadRequestException("Directory is required")
    if not request.pattern:
        raise BadRequestException("Search pattern is required")

    result = await code_dev_service.search_code(
        directory=request.directory,
        pattern=request.pattern,
        file_glob=request.file_glob,
        context_lines=request.context_lines,
        max_results=request.max_results,
    )

    return Response(
        success=result.success,
        message=result.message or "Search completed",
        data=result.model_dump(exclude={"message"}),
    )
