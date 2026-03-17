"""Repository Map Generator.

Generates a condensed map of a codebase structure for efficient LLM navigation.
Extracts file structure, classes, functions, and their relationships to provide
context without overwhelming token limits.

Usage:
    generator = RepoMapGenerator()
    repo_map = await generator.generate("/path/to/repo")
    context = repo_map.to_context_string(max_tokens=4000)
"""

import ast
import fnmatch
import logging
import re
import time
from pathlib import Path

from app.domain.exceptions.base import ResourceNotFoundException
from app.domain.models.repo_map import (
    EntryType,
    RepoMap,
    RepoMapConfig,
    RepoMapEntry,
)

logger = logging.getLogger(__name__)


# Language detection by extension
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".pyx": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".vue": "vue",
    ".svelte": "svelte",
}


class RepoMapGenerator:
    """Generates repository maps from source code."""

    def __init__(self, config: RepoMapConfig | None = None):
        """Initialize the generator.

        Args:
            config: Configuration options
        """
        self._config = config or RepoMapConfig()

    async def generate(
        self,
        root_path: str,
        specific_paths: list[str] | None = None,
    ) -> RepoMap:
        """Generate a repository map.

        Args:
            root_path: Root path of the repository
            specific_paths: If provided, only process these paths

        Returns:
            RepoMap with extracted structure
        """
        start_time = time.time()
        root = Path(root_path)

        if not root.exists():
            raise ResourceNotFoundException(
                f"Repository path does not exist: {root_path}",
                resource_type="repository",
                resource_id=root_path,
            )

        repo_map = RepoMap(
            root_path=str(root),
            generated_at=start_time,
        )

        languages: dict[str, int] = {}
        files_processed = 0
        total_lines = 0

        # Get files to process
        if specific_paths:
            files = [root / p for p in specific_paths if (root / p).exists()]
        else:
            files = list(self._find_files(root))

        for file_path in files[: self._config.max_files]:
            try:
                # Get file extension and language
                ext = file_path.suffix.lower()
                language = EXTENSION_TO_LANGUAGE.get(ext, "other")
                languages[language] = languages.get(language, 0) + 1

                # Read file
                content = file_path.read_text(errors="ignore")
                lines = len(content.splitlines())
                total_lines += lines

                # Calculate relative path
                rel_path = str(file_path.relative_to(root))

                # Calculate importance
                importance = self._calculate_importance(rel_path)

                # Add file entry
                repo_map.add_entry(
                    RepoMapEntry(
                        path=rel_path,
                        entry_type=EntryType.FILE,
                        name=file_path.name,
                        line_number=None,
                        importance=importance * 0.5,  # Files less important than definitions
                        metadata={"lines": lines, "language": language},
                    )
                )

                # Extract definitions based on language
                if language == "python" and self._config.extract_functions:
                    entries = self._extract_python_definitions(content, rel_path, importance)
                    for entry in entries:
                        repo_map.add_entry(entry)
                elif language in ("typescript", "javascript") and self._config.extract_functions:
                    entries = self._extract_js_ts_definitions(content, rel_path, importance)
                    for entry in entries:
                        repo_map.add_entry(entry)

                files_processed += 1

            except Exception as e:
                logger.debug(f"Error processing {file_path}: {e}")
                continue

        repo_map.file_count = files_processed
        repo_map.total_lines = total_lines
        repo_map.languages = languages

        logger.info(
            f"Generated repo map: {files_processed} files, "
            f"{len(repo_map.entries)} entries in {time.time() - start_time:.2f}s"
        )

        return repo_map

    def _find_files(self, root: Path, depth: int = 0) -> list[Path]:
        """Find all relevant files in the repository."""
        if depth > self._config.max_depth:
            return []

        files = []

        try:
            for item in root.iterdir():
                # Skip excluded patterns
                rel_path = str(item.relative_to(root.parent))
                if self._matches_patterns(rel_path, self._config.exclude_patterns):
                    continue

                if item.is_file():
                    if self._matches_patterns(item.name, self._config.include_patterns):
                        files.append(item)
                elif item.is_dir():
                    files.extend(self._find_files(item, depth + 1))
        except PermissionError:
            pass

        return files

    def _matches_patterns(self, path: str, patterns: list[str]) -> bool:
        """Check if a path matches any of the given patterns."""
        return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)

    def _calculate_importance(self, path: str) -> float:
        """Calculate importance score for a file."""
        importance = 1.0

        # Boost for important patterns
        for pattern in self._config.importance_boost_patterns:
            if fnmatch.fnmatch(path, pattern):
                importance *= 1.5

        # Boost for shorter paths (more central files)
        depth = path.count("/")
        importance *= max(0.5, 1.0 - depth * 0.1)

        return min(2.0, importance)

    def _extract_python_definitions(
        self,
        content: str,
        file_path: str,
        base_importance: float,
    ) -> list[RepoMapEntry]:
        """Extract class and function definitions from Python code."""
        entries = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return entries

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Extract class
                docstring = ast.get_docstring(node)
                entries.append(
                    RepoMapEntry(
                        path=file_path,
                        entry_type=EntryType.CLASS,
                        name=node.name,
                        signature=self._format_class_signature(node),
                        docstring=self._truncate_docstring(docstring) if docstring else None,
                        line_number=node.lineno,
                        importance=base_importance * 1.2,
                    )
                )

                # Extract methods
                if self._config.extract_functions:
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            method_docstring = ast.get_docstring(item)
                            entries.append(
                                RepoMapEntry(
                                    path=file_path,
                                    entry_type=EntryType.METHOD,
                                    name=item.name,
                                    signature=self._format_function_signature(item),
                                    docstring=self._truncate_docstring(method_docstring) if method_docstring else None,
                                    line_number=item.lineno,
                                    parent=node.name,
                                    importance=base_importance * (1.0 if item.name.startswith("_") else 0.8),
                                )
                            )

            elif isinstance(node, ast.FunctionDef) and not isinstance(getattr(node, "parent", None), ast.ClassDef):
                # Top-level function
                if hasattr(node, "col_offset") and node.col_offset == 0:
                    docstring = ast.get_docstring(node)
                    entries.append(
                        RepoMapEntry(
                            path=file_path,
                            entry_type=EntryType.FUNCTION,
                            name=node.name,
                            signature=self._format_function_signature(node),
                            docstring=self._truncate_docstring(docstring) if docstring else None,
                            line_number=node.lineno,
                            importance=base_importance * (1.0 if not node.name.startswith("_") else 0.6),
                        )
                    )

        return entries

    def _format_function_signature(self, node: ast.FunctionDef) -> str:
        """Format a function signature from AST."""
        args = []

        # Regular args
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation) if hasattr(ast, 'unparse') else '...'}"
            args.append(arg_str)

        # *args
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")

        # **kwargs
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")

        # Return type
        returns = ""
        if node.returns:
            try:
                returns = f" -> {ast.unparse(node.returns)}" if hasattr(ast, "unparse") else " -> ..."
            except Exception:
                returns = " -> ..."

        return f"{node.name}({', '.join(args)}){returns}"

    def _format_class_signature(self, node: ast.ClassDef) -> str:
        """Format a class signature from AST."""
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base) if hasattr(ast, "unparse") else "...")
            except Exception:
                bases.append("...")

        if bases:
            return f"class {node.name}({', '.join(bases)})"
        return f"class {node.name}"

    def _extract_js_ts_definitions(
        self,
        content: str,
        file_path: str,
        base_importance: float,
    ) -> list[RepoMapEntry]:
        """Extract class and function definitions from JavaScript/TypeScript code.

        Uses regex patterns since we don't have a JS parser.
        """
        entries = []

        # Class pattern
        class_pattern = re.compile(
            r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+[\w,\s]+)?",
            re.MULTILINE,
        )

        for match in class_pattern.finditer(content):
            line_number = content[: match.start()].count("\n") + 1
            class_name = match.group(1)
            extends = match.group(2)

            signature = f"class {class_name}"
            if extends:
                signature += f" extends {extends}"

            entries.append(
                RepoMapEntry(
                    path=file_path,
                    entry_type=EntryType.CLASS,
                    name=class_name,
                    signature=signature,
                    line_number=line_number,
                    importance=base_importance * 1.2,
                )
            )

        # Function patterns
        func_patterns = [
            # function name() or async function name()
            re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
            # const name = () => or const name = function()
            re.compile(
                r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=]+)\s*=>\s*", re.MULTILINE
            ),
        ]

        for pattern in func_patterns:
            for match in pattern.finditer(content):
                line_number = content[: match.start()].count("\n") + 1
                func_name = match.group(1)

                # Skip if inside a class (basic heuristic)
                preceding = content[: match.start()]
                if preceding.count("{") > preceding.count("}"):
                    continue

                entries.append(
                    RepoMapEntry(
                        path=file_path,
                        entry_type=EntryType.FUNCTION,
                        name=func_name,
                        signature=f"function {func_name}(...)",
                        line_number=line_number,
                        importance=base_importance * (1.0 if not func_name.startswith("_") else 0.6),
                    )
                )

        # Interface pattern (TypeScript)
        interface_pattern = re.compile(r"^(?:export\s+)?interface\s+(\w+)", re.MULTILINE)

        for match in interface_pattern.finditer(content):
            line_number = content[: match.start()].count("\n") + 1
            entries.append(
                RepoMapEntry(
                    path=file_path,
                    entry_type=EntryType.INTERFACE,
                    name=match.group(1),
                    signature=f"interface {match.group(1)}",
                    line_number=line_number,
                    importance=base_importance * 1.1,
                )
            )

        return entries

    def _truncate_docstring(self, docstring: str, max_length: int = 100) -> str:
        """Truncate a docstring to first sentence or max length."""
        if not docstring:
            return ""

        # Get first line
        first_line = docstring.split("\n")[0].strip()

        # Truncate if needed
        if len(first_line) > max_length:
            return first_line[: max_length - 3] + "..."

        return first_line

    def to_context_string(
        self,
        repo_map: RepoMap,
        max_tokens: int = 4000,
    ) -> str:
        """Convert a repo map to a context string for LLM.

        Convenience method that calls repo_map.to_context_string().
        """
        return repo_map.to_context_string(max_tokens=max_tokens)


# Global instance
_repo_map_generator: RepoMapGenerator | None = None


def get_repo_map_generator() -> RepoMapGenerator:
    """Get the global repo map generator instance."""
    global _repo_map_generator
    if _repo_map_generator is None:
        _repo_map_generator = RepoMapGenerator()
    return _repo_map_generator
