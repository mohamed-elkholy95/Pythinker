"""
Test Runner request/response schemas for API endpoints
"""
from pydantic import BaseModel, Field
from typing import Optional
from app.models.test_runner import TestFramework


class TestRunRequest(BaseModel):
    """Request to run tests"""
    path: str = Field(..., description="Path to test file or directory")
    framework: Optional[TestFramework] = Field(
        default=TestFramework.AUTO,
        description="Test framework to use (auto-detects if not specified)"
    )
    pattern: Optional[str] = Field(
        None,
        description="Pattern to match test names/files (e.g., 'test_*.py', '*_test.js')"
    )
    coverage: Optional[bool] = Field(
        default=False,
        description="Whether to collect code coverage"
    )
    timeout: Optional[int] = Field(
        default=300,
        ge=10,
        le=1800,
        description="Test timeout in seconds (10-1800)"
    )
    verbose: Optional[bool] = Field(
        default=False,
        description="Verbose output"
    )


class TestListRequest(BaseModel):
    """Request to list available tests"""
    path: str = Field(..., description="Path to test file or directory")
    framework: Optional[TestFramework] = Field(
        default=TestFramework.AUTO,
        description="Test framework (auto-detects if not specified)"
    )


class CoverageReportRequest(BaseModel):
    """Request to generate coverage report"""
    path: str = Field(..., description="Path to source code directory")
    output_format: Optional[str] = Field(
        default="html",
        description="Report format: 'html', 'xml', 'json'"
    )
    output_dir: Optional[str] = Field(
        None,
        description="Output directory for report (defaults to workspace output)"
    )
