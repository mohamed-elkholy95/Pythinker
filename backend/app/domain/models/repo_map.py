"""Repository Map Domain Models.

Data structures for representing codebase structure and navigation.
The repo map provides a condensed view of a repository's structure,
including files, classes, functions, and their relationships.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntryType(str, Enum):
    """Types of repository entries."""

    FILE = "file"
    DIRECTORY = "directory"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    MODULE = "module"
    CONSTANT = "constant"
    TYPE = "type"


@dataclass
class RepoMapEntry:
    """A single entry in the repository map."""

    path: str
    """File or directory path relative to repo root."""

    entry_type: EntryType
    """Type of the entry."""

    name: str
    """Name of the entry (class name, function name, etc.)."""

    signature: str | None = None
    """Function/method signature if applicable."""

    docstring: str | None = None
    """First line or summary of docstring."""

    line_number: int | None = None
    """Line number where the entry is defined."""

    parent: str | None = None
    """Parent entry (e.g., class name for a method)."""

    references: list[str] = field(default_factory=list)
    """List of other entries this one references."""

    importance: float = 1.0
    """Relative importance score (higher = more important)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "entry_type": self.entry_type.value,
            "name": self.name,
            "signature": self.signature,
            "docstring": self.docstring,
            "line_number": self.line_number,
            "parent": self.parent,
            "references": self.references,
            "importance": self.importance,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoMapEntry":
        return cls(
            path=data["path"],
            entry_type=EntryType(data["entry_type"]),
            name=data["name"],
            signature=data.get("signature"),
            docstring=data.get("docstring"),
            line_number=data.get("line_number"),
            parent=data.get("parent"),
            references=data.get("references", []),
            importance=data.get("importance", 1.0),
            metadata=data.get("metadata", {}),
        )

    def to_context_line(self, include_signature: bool = True) -> str:
        """Convert to a single line for context.

        Returns a compact representation suitable for LLM context.
        """
        parts = []

        # Path and line number
        if self.line_number:
            parts.append(f"{self.path}:{self.line_number}")
        else:
            parts.append(self.path)

        # Type indicator
        type_indicators = {
            EntryType.CLASS: "class",
            EntryType.FUNCTION: "def",
            EntryType.METHOD: "def",
            EntryType.INTERFACE: "interface",
            EntryType.CONSTANT: "const",
            EntryType.TYPE: "type",
        }
        indicator = type_indicators.get(self.entry_type, "")

        # Name with optional signature
        if self.entry_type in (EntryType.FILE, EntryType.DIRECTORY):
            parts.append(self.name)
        elif include_signature and self.signature:
            parts.append(f"{indicator} {self.signature}")
        else:
            parts.append(f"{indicator} {self.name}")

        # Docstring summary
        if self.docstring:
            # Truncate docstring to first sentence or 60 chars
            doc = self.docstring.split("\n")[0][:60]
            if len(doc) < len(self.docstring):
                doc += "..."
            parts.append(f"# {doc}")

        return " ".join(parts)


@dataclass
class RepoMap:
    """Complete repository map."""

    root_path: str
    """Root path of the repository."""

    entries: list[RepoMapEntry] = field(default_factory=list)
    """All entries in the map."""

    file_count: int = 0
    """Total number of files."""

    total_lines: int = 0
    """Approximate total lines of code."""

    languages: dict[str, int] = field(default_factory=dict)
    """File count by language/extension."""

    generated_at: float = 0.0
    """Unix timestamp when the map was generated."""

    version: str = "1.0"
    """Schema version."""

    def add_entry(self, entry: RepoMapEntry) -> None:
        """Add an entry to the map."""
        self.entries.append(entry)

    def get_by_type(self, entry_type: EntryType) -> list[RepoMapEntry]:
        """Get all entries of a specific type."""
        return [e for e in self.entries if e.entry_type == entry_type]

    def get_by_path(self, path: str) -> list[RepoMapEntry]:
        """Get all entries in a specific file path."""
        return [e for e in self.entries if e.path == path]

    def get_important_entries(self, min_importance: float = 0.5) -> list[RepoMapEntry]:
        """Get entries above a certain importance threshold."""
        return sorted(
            [e for e in self.entries if e.importance >= min_importance],
            key=lambda e: e.importance,
            reverse=True,
        )

    def to_context_string(
        self,
        max_tokens: int = 4000,
        include_signatures: bool = True,
        min_importance: float = 0.3,
    ) -> str:
        """Convert to a context string for LLM consumption.

        Args:
            max_tokens: Approximate max tokens (chars / 4)
            include_signatures: Include function signatures
            min_importance: Minimum importance to include

        Returns:
            Formatted string representation of the repo map
        """
        lines = [f"# Repository Map: {self.root_path}"]
        lines.append(f"# Files: {self.file_count}, Languages: {', '.join(self.languages.keys())}")
        lines.append("")

        # Sort by path and then importance
        sorted_entries = sorted(
            [e for e in self.entries if e.importance >= min_importance],
            key=lambda e: (e.path, -e.importance),
        )

        current_path = ""
        chars_used = len("\n".join(lines))
        max_chars = max_tokens * 4

        for entry in sorted_entries:
            # Add file header if path changed
            if entry.path != current_path:
                current_path = entry.path
                file_header = f"\n## {current_path}"
                if chars_used + len(file_header) > max_chars:
                    lines.append("\n... (truncated)")
                    break
                lines.append(file_header)
                chars_used += len(file_header) + 1

            # Add entry line
            line = entry.to_context_line(include_signatures)
            if chars_used + len(line) > max_chars:
                lines.append("... (truncated)")
                break
            lines.append(f"  {line}")
            chars_used += len(line) + 3

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_path": self.root_path,
            "entries": [e.to_dict() for e in self.entries],
            "file_count": self.file_count,
            "total_lines": self.total_lines,
            "languages": self.languages,
            "generated_at": self.generated_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoMap":
        return cls(
            root_path=data["root_path"],
            entries=[RepoMapEntry.from_dict(e) for e in data.get("entries", [])],
            file_count=data.get("file_count", 0),
            total_lines=data.get("total_lines", 0),
            languages=data.get("languages", {}),
            generated_at=data.get("generated_at", 0.0),
            version=data.get("version", "1.0"),
        )


@dataclass
class RepoMapConfig:
    """Configuration for repo map generation."""

    max_files: int = 1000
    """Maximum number of files to process."""

    max_depth: int = 10
    """Maximum directory depth."""

    include_patterns: list[str] = field(
        default_factory=lambda: [
            "*.py",
            "*.ts",
            "*.tsx",
            "*.js",
            "*.jsx",
            "*.java",
            "*.go",
            "*.rs",
            "*.rb",
            "*.php",
            "*.c",
            "*.cpp",
            "*.h",
            "*.hpp",
        ]
    )
    """Glob patterns for files to include."""

    exclude_patterns: list[str] = field(
        default_factory=lambda: [
            "node_modules/*",
            "__pycache__/*",
            "*.pyc",
            ".git/*",
            "dist/*",
            "build/*",
            ".venv/*",
            "venv/*",
            "*.min.js",
            "*.map",
        ]
    )
    """Glob patterns for files to exclude."""

    extract_classes: bool = True
    """Extract class definitions."""

    extract_functions: bool = True
    """Extract function definitions."""

    extract_docstrings: bool = True
    """Extract docstrings for entries."""

    importance_boost_patterns: list[str] = field(
        default_factory=lambda: [
            "**/main.py",
            "**/app.py",
            "**/index.*",
            "**/config.*",
            "**/settings.*",
            "**/routes.*",
            "**/api.*",
        ]
    )
    """Patterns for files that get importance boost."""
