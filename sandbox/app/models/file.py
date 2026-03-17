"""
File operation related models
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class FileReadResult(BaseModel):
    """File read result"""

    content: str = Field(..., description="File content")
    file: str = Field(..., description="Path of the read file")


class FileWriteResult(BaseModel):
    """File write result"""

    file: str = Field(..., description="Path of the written file")
    bytes_written: Optional[int] = Field(None, description="Number of bytes written")


class FileReplaceResult(BaseModel):
    """File content replacement result"""

    file: str = Field(..., description="Path of the operated file")
    replaced_count: int = Field(0, description="Number of replacements")


class FileSearchResult(BaseModel):
    """File content search result"""

    file: str = Field(..., description="Path of the searched file")
    matches: List[str] = Field([], description="List of matched content")
    line_numbers: List[int] = Field([], description="List of matched line numbers")


class FileFindResult(BaseModel):
    """File find result"""

    path: str = Field(..., description="Path of the search directory")
    files: List[str] = Field([], description="List of found files")


class FileUploadResult(BaseModel):
    """File upload result"""

    file_path: str = Field(..., description="Path of the uploaded file")
    file_size: int = Field(..., description="Size of the uploaded file in bytes")
    success: bool = Field(..., description="Whether upload was successful")


class FileDeleteResult(BaseModel):
    """File deletion result."""

    path: str = Field(..., description="Path of the deleted target")
    deleted: bool = Field(..., description="Whether deletion was successful")


class FileListEntry(BaseModel):
    """Directory entry metadata."""

    name: str = Field(..., description="Base name of the entry")
    path: str = Field(..., description="Absolute path to the entry")
    is_dir: bool = Field(..., description="Whether the entry is a directory")
    size_bytes: int = Field(..., description="Entry size in bytes (0 for directories)")


class FileListResult(BaseModel):
    """Directory listing result."""

    path: str = Field(..., description="Path of the listed directory")
    entries: List[FileListEntry] = Field([], description="Directory entries")
