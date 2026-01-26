"""
Export request/response schemas for API endpoints
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from app.models.export import ReportType, ReportFormat, FileCategory


class OrganizeRequest(BaseModel):
    """Request to organize files"""
    session_id: str = Field(..., description="Session ID")
    source_path: str = Field(..., description="Path to file or directory to organize")
    target_category: Optional[FileCategory] = Field(
        default=FileCategory.OTHER,
        description="Target category for organization"
    )


class ArchiveRequest(BaseModel):
    """Request to create archive"""
    session_id: str = Field(..., description="Session ID")
    name: str = Field(..., description="Archive name (without extension)")
    include_patterns: Optional[List[str]] = Field(
        default=["**/*"],
        description="Glob patterns to include (e.g., ['src/**', 'tests/**'])"
    )
    exclude_patterns: Optional[List[str]] = Field(
        default=[".git/**", "__pycache__/**", "node_modules/**", ".pythinker/**"],
        description="Glob patterns to exclude"
    )
    base_path: Optional[str] = Field(
        None,
        description="Base path for files (defaults to workspace root)"
    )


class ReportRequest(BaseModel):
    """Request to generate report"""
    session_id: str = Field(..., description="Session ID")
    report_type: Optional[ReportType] = Field(
        default=ReportType.SUMMARY,
        description="Type of report: summary, test, security, full"
    )
    output_format: Optional[ReportFormat] = Field(
        default=ReportFormat.MARKDOWN,
        description="Output format: markdown, html, json"
    )
    title: Optional[str] = Field(
        default="Workspace Report",
        description="Report title"
    )
    include_sections: Optional[List[str]] = Field(
        None,
        description="Specific sections to include (optional)"
    )


class ExportListRequest(BaseModel):
    """Request to list exports"""
    session_id: str = Field(..., description="Session ID")
