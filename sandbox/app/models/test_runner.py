"""
Test Runner business model definitions
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class TestFramework(str, Enum):
    """Supported test frameworks"""
    AUTO = "auto"
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    MOCHA = "mocha"
    NPM_TEST = "npm_test"


class TestStatus(str, Enum):
    """Test execution status"""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TestFailure(BaseModel):
    """Details of a test failure"""
    test_name: str = Field(..., description="Name of the failed test")
    file_path: str = Field(default="", description="File containing the test")
    line_number: int = Field(default=0, description="Line number of failure")
    error_type: str = Field(default="", description="Type of error/exception")
    error_message: str = Field(..., description="Error message")
    traceback: Optional[str] = Field(None, description="Stack trace")


class TestResult(BaseModel):
    """Result of test execution"""
    framework: str = Field(..., description="Test framework used")
    total_tests: int = Field(default=0, description="Total number of tests")
    passed: int = Field(default=0, description="Number of passed tests")
    failed: int = Field(default=0, description="Number of failed tests")
    skipped: int = Field(default=0, description="Number of skipped tests")
    errors: int = Field(default=0, description="Number of errors (not failures)")
    duration_ms: int = Field(default=0, description="Total duration in milliseconds")
    coverage_percent: Optional[float] = Field(None, description="Code coverage percentage")
    failures: List[TestFailure] = Field(default_factory=list, description="Details of failures")
    report_path: Optional[str] = Field(None, description="Path to detailed report")
    output: Optional[str] = Field(None, description="Test output/logs")
    success: bool = Field(default=False, description="Whether all tests passed")
    message: Optional[str] = Field(None, description="Status message")


class TestInfo(BaseModel):
    """Information about a single test"""
    name: str = Field(..., description="Test name")
    file_path: str = Field(default="", description="File path")
    class_name: Optional[str] = Field(None, description="Test class if applicable")
    line_number: int = Field(default=0, description="Line number")


class TestListResult(BaseModel):
    """Result of test listing operation"""
    framework: str = Field(..., description="Detected/specified framework")
    tests: List[TestInfo] = Field(default_factory=list, description="List of tests")
    total_count: int = Field(default=0, description="Total number of tests")
    files_count: int = Field(default=0, description="Number of test files")
    message: Optional[str] = Field(None, description="Status message")


class CoverageResult(BaseModel):
    """Result of coverage analysis"""
    total_lines: int = Field(default=0, description="Total lines of code")
    covered_lines: int = Field(default=0, description="Lines covered by tests")
    coverage_percent: float = Field(default=0.0, description="Coverage percentage")
    uncovered_files: List[str] = Field(default_factory=list, description="Files with no coverage")
    file_coverage: Dict[str, float] = Field(default_factory=dict, description="Per-file coverage")
    report_path: Optional[str] = Field(None, description="Path to HTML report")
    message: Optional[str] = Field(None, description="Status message")
