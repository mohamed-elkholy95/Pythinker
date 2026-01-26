"""
Code Development request/response schemas for API endpoints
"""
from pydantic import BaseModel, Field
from typing import Optional
from app.models.code_dev import Formatter, Linter, AnalysisType


class CodeFormatRequest(BaseModel):
    """Request to format code"""
    file_path: str = Field(..., description="Path to file to format")
    formatter: Optional[Formatter] = Field(
        default=Formatter.AUTO,
        description="Formatter to use (auto detects from file extension)"
    )
    check_only: Optional[bool] = Field(
        default=False,
        description="Check formatting without modifying file"
    )


class CodeLintRequest(BaseModel):
    """Request to lint code"""
    path: str = Field(..., description="Path to file or directory to lint")
    linter: Optional[Linter] = Field(
        default=Linter.AUTO,
        description="Linter to use (auto detects from file type)"
    )
    fix: Optional[bool] = Field(
        default=False,
        description="Automatically fix issues where possible"
    )


class CodeAnalyzeRequest(BaseModel):
    """Request to analyze code"""
    path: str = Field(..., description="Path to file or directory to analyze")
    analysis_type: Optional[AnalysisType] = Field(
        default=AnalysisType.ALL,
        description="Type of analysis: security, complexity, or all"
    )


class CodeSearchRequest(BaseModel):
    """Request to search code"""
    directory: str = Field(..., description="Directory to search in")
    pattern: str = Field(..., description="Search pattern (regex supported)")
    file_glob: Optional[str] = Field(
        default="*",
        description="Glob pattern to filter files (e.g., '*.py', '*.js')"
    )
    context_lines: Optional[int] = Field(
        default=2,
        ge=0,
        le=10,
        description="Number of context lines before/after match"
    )
    max_results: Optional[int] = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of results"
    )
