"""
Export business model definitions
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class ReportType(str, Enum):
    """Types of reports that can be generated"""
    SUMMARY = "summary"
    TEST = "test"
    SECURITY = "security"
    FULL = "full"


class ReportFormat(str, Enum):
    """Output formats for reports"""
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"


class FileCategory(str, Enum):
    """File organization categories"""
    SOURCE = "source"
    TEST = "test"
    DOCS = "docs"
    CONFIG = "config"
    OUTPUT = "output"
    OTHER = "other"


class OrganizeResult(BaseModel):
    """Result of file organization operation"""
    success: bool = Field(..., description="Whether organization succeeded")
    source_path: str = Field(..., description="Original source path")
    target_path: str = Field(..., description="Target path after organization")
    category: str = Field(..., description="Category assigned")
    files_moved: int = Field(default=0, description="Number of files moved")
    message: Optional[str] = Field(None, description="Status message")


class ArchiveResult(BaseModel):
    """Result of archive creation"""
    success: bool = Field(..., description="Whether archive was created")
    archive_path: str = Field(..., description="Path to created archive")
    archive_name: str = Field(..., description="Name of archive file")
    format: str = Field(default="zip", description="Archive format")
    size_bytes: int = Field(default=0, description="Archive size in bytes")
    files_count: int = Field(default=0, description="Number of files archived")
    included: List[str] = Field(default_factory=list, description="Patterns included")
    excluded: List[str] = Field(default_factory=list, description="Patterns excluded")
    message: Optional[str] = Field(None, description="Status message")


class ReportSection(BaseModel):
    """Section of a report"""
    title: str = Field(..., description="Section title")
    content: str = Field(..., description="Section content")
    level: int = Field(default=2, description="Heading level (1-6)")


class ReportResult(BaseModel):
    """Result of report generation"""
    success: bool = Field(..., description="Whether report was generated")
    report_path: str = Field(..., description="Path to report file")
    report_type: str = Field(..., description="Type of report")
    format: str = Field(..., description="Output format")
    sections: List[str] = Field(default_factory=list, description="Report sections")
    generated_at: str = Field(..., description="Generation timestamp")
    message: Optional[str] = Field(None, description="Status message")


class ExportItem(BaseModel):
    """Single export item"""
    name: str = Field(..., description="File/archive name")
    path: str = Field(..., description="Full path")
    type: str = Field(..., description="Type: 'file' or 'archive'")
    size_bytes: int = Field(default=0, description="Size in bytes")
    created_at: str = Field(..., description="Creation timestamp")


class ExportListResult(BaseModel):
    """Result of listing available exports"""
    session_id: str = Field(..., description="Session ID")
    exports_path: str = Field(..., description="Path to exports directory")
    items: List[ExportItem] = Field(default_factory=list, description="Available exports")
    total_count: int = Field(default=0, description="Total number of exports")
    total_size_bytes: int = Field(default=0, description="Total size of all exports")
