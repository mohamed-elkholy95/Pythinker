"""
Code Development business model definitions
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class Formatter(str, Enum):
    """Supported code formatters"""

    AUTO = "auto"
    BLACK = "black"
    ISORT = "isort"
    AUTOPEP8 = "autopep8"
    PRETTIER = "prettier"


class Linter(str, Enum):
    """Supported code linters"""

    AUTO = "auto"
    FLAKE8 = "flake8"
    PYLINT = "pylint"
    MYPY = "mypy"
    ESLINT = "eslint"


class AnalysisType(str, Enum):
    """Types of code analysis"""

    SECURITY = "security"
    COMPLEXITY = "complexity"
    ALL = "all"


class FormatResult(BaseModel):
    """Result of code formatting operation"""

    success: bool = Field(..., description="Whether formatting succeeded")
    file_path: str = Field(..., description="Path to formatted file")
    formatter: str = Field(..., description="Formatter used")
    changed: bool = Field(default=False, description="Whether file was modified")
    diff: Optional[str] = Field(None, description="Diff of changes if check_only mode")
    message: Optional[str] = Field(None, description="Status message")


class LintIssue(BaseModel):
    """Single lint issue"""

    file: str = Field(..., description="File path")
    line: int = Field(..., description="Line number")
    column: int = Field(default=0, description="Column number")
    code: str = Field(default="", description="Error/warning code")
    message: str = Field(..., description="Issue description")
    severity: str = Field(
        default="warning", description="Severity: error, warning, info"
    )


class LintResult(BaseModel):
    """Result of code linting operation"""

    success: bool = Field(..., description="Whether linting completed without errors")
    path: str = Field(..., description="Path that was linted")
    linter: str = Field(..., description="Linter used")
    issues: List[LintIssue] = Field(
        default_factory=list, description="List of issues found"
    )
    issues_count: int = Field(default=0, description="Total number of issues")
    errors_count: int = Field(default=0, description="Number of errors")
    warnings_count: int = Field(default=0, description="Number of warnings")
    fixed_count: int = Field(
        default=0, description="Number of issues auto-fixed (if --fix)"
    )
    message: Optional[str] = Field(None, description="Status message")


class SecurityIssue(BaseModel):
    """Security vulnerability found"""

    file: str = Field(..., description="File path")
    line: int = Field(..., description="Line number")
    issue_id: str = Field(default="", description="Issue identifier")
    severity: str = Field(default="medium", description="Severity: low, medium, high")
    confidence: str = Field(
        default="medium", description="Confidence: low, medium, high"
    )
    issue_text: str = Field(..., description="Issue description")
    cwe: Optional[str] = Field(None, description="CWE identifier if applicable")


class AnalysisResult(BaseModel):
    """Result of code analysis operation"""

    success: bool = Field(..., description="Whether analysis completed")
    path: str = Field(..., description="Path that was analyzed")
    analysis_type: str = Field(..., description="Type of analysis performed")
    security_issues: List[SecurityIssue] = Field(
        default_factory=list, description="Security issues found"
    )
    security_score: Optional[float] = Field(None, description="Security score (0-100)")
    complexity_score: Optional[float] = Field(None, description="Complexity score")
    summary: Dict[str, Any] = Field(
        default_factory=dict, description="Analysis summary"
    )
    message: Optional[str] = Field(None, description="Status message")


class SearchMatch(BaseModel):
    """Single search match"""

    file: str = Field(..., description="File path")
    line: int = Field(..., description="Line number")
    content: str = Field(..., description="Matching line content")
    context_before: List[str] = Field(
        default_factory=list, description="Lines before match"
    )
    context_after: List[str] = Field(
        default_factory=list, description="Lines after match"
    )


class SearchResult(BaseModel):
    """Result of code search operation"""

    success: bool = Field(..., description="Whether search completed")
    pattern: str = Field(..., description="Search pattern used")
    directory: str = Field(..., description="Directory searched")
    matches: List[SearchMatch] = Field(
        default_factory=list, description="Search matches"
    )
    total_matches: int = Field(default=0, description="Total number of matches")
    files_searched: int = Field(default=0, description="Number of files searched")
    message: Optional[str] = Field(None, description="Status message")
