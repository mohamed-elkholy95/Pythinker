"""GitHub Skill Seeker Tool.

This tool analyzes GitHub repositories and packages them as agent skills.
Inspired by Manus github-gem-seeker pattern for discovering and extracting
reusable capabilities from open-source projects.

Features:
- Repository cloning and analysis
- AST parsing for Python code
- README and docstring extraction
- Automatic SKILL.md generation
- Usage example generation
"""

import ast
import asyncio
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from app.domain.models.skill_package import (
    SkillExample,
    SkillFeatureCategory,
    SkillFeatureMapping,
    SkillPackage,
    SkillPackageFile,
    SkillPackageMetadata,
    SkillWorkflowStep,
)
from app.domain.services.skill_packager import get_skill_packager
from app.domain.services.tools.base import BaseTool, ToolResult, ToolSchema


@dataclass
class ExtractedFunction:
    """Function extracted from source code."""

    name: str
    docstring: str | None
    parameters: list[tuple[str, str | None]]  # (name, type_hint)
    return_type: str | None
    is_async: bool
    decorators: list[str]
    line_number: int
    source_file: str


@dataclass
class ExtractedClass:
    """Class extracted from source code."""

    name: str
    docstring: str | None
    methods: list[ExtractedFunction]
    base_classes: list[str]
    decorators: list[str]
    line_number: int
    source_file: str


@dataclass
class RepositoryAnalysis:
    """Analysis results for a repository."""

    name: str
    description: str
    readme_content: str | None
    main_module: str | None
    functions: list[ExtractedFunction] = field(default_factory=list)
    classes: list[ExtractedClass] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    examples_found: list[str] = field(default_factory=list)


class PythonASTAnalyzer:
    """Analyzes Python source code using AST parsing."""

    def __init__(self) -> None:
        """Initialize the analyzer."""
        self.functions: list[ExtractedFunction] = []
        self.classes: list[ExtractedClass] = []

    def analyze_file(self, file_path: Path, source_file: str) -> None:
        """Analyze a Python file.

        Args:
            file_path: Path to the Python file
            source_file: Relative path for recording
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            self._visit_module(tree, source_file)
        except (SyntaxError, UnicodeDecodeError):
            # Skip files that can't be parsed
            pass

    def _visit_module(self, tree: ast.Module, source_file: str) -> None:
        """Visit all nodes in the module."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                self._extract_function(node, source_file)
            elif isinstance(node, ast.ClassDef):
                self._extract_class(node, source_file)

    def _extract_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, source_file: str) -> None:
        """Extract function information."""
        # Skip private functions (starting with _)
        if node.name.startswith("_") and not node.name.startswith("__"):
            return

        # Get docstring
        docstring = ast.get_docstring(node)

        # Extract parameters
        params: list[tuple[str, str | None]] = []
        for arg in node.args.args:
            type_hint = None
            if arg.annotation:
                type_hint = ast.unparse(arg.annotation)
            params.append((arg.arg, type_hint))

        # Get return type
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)

        # Get decorators
        decorators = [ast.unparse(d) for d in node.decorator_list]

        func = ExtractedFunction(
            name=node.name,
            docstring=docstring,
            parameters=params,
            return_type=return_type,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=decorators,
            line_number=node.lineno,
            source_file=source_file,
        )
        self.functions.append(func)

    def _extract_class(self, node: ast.ClassDef, source_file: str) -> None:
        """Extract class information."""
        # Skip private classes
        if node.name.startswith("_"):
            return

        # Get docstring
        docstring = ast.get_docstring(node)

        # Get base classes
        bases = [ast.unparse(b) for b in node.bases]

        # Get decorators
        decorators = [ast.unparse(d) for d in node.decorator_list]

        # Extract methods
        methods: list[ExtractedFunction] = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and (
                not item.name.startswith("_") or item.name in ["__init__", "__call__"]
            ):
                func = self._create_function(item, source_file)
                if func:
                    methods.append(func)

        cls = ExtractedClass(
            name=node.name,
            docstring=docstring,
            methods=methods,
            base_classes=bases,
            decorators=decorators,
            line_number=node.lineno,
            source_file=source_file,
        )
        self.classes.append(cls)

    def _create_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, source_file: str
    ) -> ExtractedFunction | None:
        """Create an ExtractedFunction from an AST node."""
        docstring = ast.get_docstring(node)

        params: list[tuple[str, str | None]] = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            type_hint = None
            if arg.annotation:
                type_hint = ast.unparse(arg.annotation)
            params.append((arg.arg, type_hint))

        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)

        decorators = [ast.unparse(d) for d in node.decorator_list]

        return ExtractedFunction(
            name=node.name,
            docstring=docstring,
            parameters=params,
            return_type=return_type,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=decorators,
            line_number=node.lineno,
            source_file=source_file,
        )


class GitHubSkillSeeker(BaseTool):
    """Tool for discovering and packaging GitHub repositories as skills.

    Analyzes repositories, extracts API documentation via AST parsing,
    generates SKILL.md with examples, and packages for agent deployment.
    """

    name = "github_skill_seeker"
    description = "Analyze GitHub repositories and create agent skills from them"

    tools: ClassVar[list[ToolSchema]] = [
        ToolSchema(
            name="github_discover_skill",
            description=(
                "Analyze a GitHub repository and discover its capabilities. "
                "Extracts functions, classes, documentation, and generates a skill package. "
                "Use this when you want to turn a GitHub repo into a reusable agent skill."
            ),
            parameters={
                "repo_url": {
                    "type": "string",
                    "description": (
                        "GitHub repository URL (e.g., https://github.com/owner/repo). Can also be owner/repo format."
                    ),
                },
                "skill_name": {
                    "type": "string",
                    "description": "Name for the generated skill (optional, defaults to repo name)",
                },
                "focus_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific paths to focus analysis on (e.g., ['src/', 'lib/'])",
                },
                "include_examples": {
                    "type": "boolean",
                    "description": "Whether to include usage examples in the skill package",
                    "default": True,
                },
            },
            required=["repo_url"],
        ),
        ToolSchema(
            name="github_analyze_readme",
            description=(
                "Extract structured information from a repository's README. "
                "Useful for understanding a project's purpose and usage patterns."
            ),
            parameters={
                "repo_url": {
                    "type": "string",
                    "description": "GitHub repository URL",
                },
            },
            required=["repo_url"],
        ),
    ]

    def __init__(self) -> None:
        """Initialize the skill seeker."""
        super().__init__()
        self._packager = get_skill_packager()

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Execute a skill seeker tool."""
        if tool_name == "github_discover_skill":
            return await self._discover_skill(
                repo_url=tool_input["repo_url"],
                skill_name=tool_input.get("skill_name"),
                focus_paths=tool_input.get("focus_paths", []),
                include_examples=tool_input.get("include_examples", True),
            )
        if tool_name == "github_analyze_readme":
            return await self._analyze_readme(repo_url=tool_input["repo_url"])
        return ToolResult(
            success=False,
            result=f"Unknown tool: {tool_name}",
        )

    async def _discover_skill(
        self,
        repo_url: str,
        skill_name: str | None,
        focus_paths: list[str],
        include_examples: bool,
    ) -> ToolResult:
        """Discover and package a GitHub repository as a skill."""
        try:
            # Normalize repo URL
            repo_url = self._normalize_repo_url(repo_url)

            # Clone repository to temp directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Clone the repository
                clone_success = await self._clone_repository(repo_url, temp_path)
                if not clone_success:
                    return ToolResult(
                        success=False,
                        result=f"Failed to clone repository: {repo_url}",
                    )

                # Analyze the repository
                analysis = await self._analyze_repository(temp_path, focus_paths)

                # Generate skill name if not provided
                if not skill_name:
                    skill_name = analysis.name.replace("-", "_").replace(" ", "_")

                # Generate the skill package
                package = self._generate_skill_package(
                    analysis=analysis,
                    skill_name=skill_name,
                    repo_url=repo_url,
                    include_examples=include_examples,
                )

                return ToolResult(
                    success=True,
                    result=self._format_discovery_result(package, analysis),
                    data={
                        "package_summary": package.summary,
                        "analysis": {
                            "name": analysis.name,
                            "description": analysis.description,
                            "functions_count": len(analysis.functions),
                            "classes_count": len(analysis.classes),
                            "dependencies": analysis.dependencies,
                        },
                    },
                )

        except Exception as e:
            return ToolResult(
                success=False,
                result=f"Failed to discover skill from repository: {e!s}",
            )

    async def _analyze_readme(self, repo_url: str) -> ToolResult:
        """Analyze a repository's README file."""
        try:
            repo_url = self._normalize_repo_url(repo_url)

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                clone_success = await self._clone_repository(repo_url, temp_path)
                if not clone_success:
                    return ToolResult(
                        success=False,
                        result=f"Failed to clone repository: {repo_url}",
                    )

                # Find README
                readme_content = self._find_and_read_readme(temp_path)
                if not readme_content:
                    return ToolResult(
                        success=False,
                        result="No README found in repository",
                    )

                # Extract structured info from README
                info = self._extract_readme_info(readme_content)

                return ToolResult(
                    success=True,
                    result=self._format_readme_analysis(info),
                    data=info,
                )

        except Exception as e:
            return ToolResult(
                success=False,
                result=f"Failed to analyze README: {e!s}",
            )

    def _normalize_repo_url(self, url: str) -> str:
        """Normalize repository URL to full GitHub URL."""
        url = url.strip()

        # Handle owner/repo format
        if "/" in url and "://" not in url and "github.com" not in url:
            return f"https://github.com/{url}"

        # Ensure HTTPS
        if url.startswith("git@github.com:"):
            url = url.replace("git@github.com:", "https://github.com/")

        # Remove .git suffix
        if url.endswith(".git"):
            url = url[:-4]

        return url

    async def _clone_repository(self, repo_url: str, dest_path: Path) -> bool:
        """Clone a repository to the destination path."""
        try:
            # Use shallow clone for faster cloning
            process = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--depth",
                "1",
                repo_url,
                str(dest_path / "repo"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            return process.returncode == 0
        except Exception:
            return False

    async def _analyze_repository(self, temp_path: Path, focus_paths: list[str]) -> RepositoryAnalysis:
        """Analyze a cloned repository."""
        repo_path = temp_path / "repo"

        # Get repository name from directory
        name = self._extract_repo_name(repo_path)

        # Read README
        readme_content = self._find_and_read_readme(repo_path)
        description = self._extract_description(readme_content) if readme_content else ""

        # Find main module
        main_module = self._find_main_module(repo_path)

        # Parse Python files
        analyzer = PythonASTAnalyzer()
        python_files = self._find_python_files(repo_path, focus_paths)
        for py_file in python_files:
            rel_path = str(py_file.relative_to(repo_path))
            analyzer.analyze_file(py_file, rel_path)

        # Extract dependencies
        dependencies = self._extract_dependencies(repo_path)

        # Find entry points
        entry_points = self._find_entry_points(repo_path)

        # Find examples
        examples = self._find_example_files(repo_path)

        return RepositoryAnalysis(
            name=name,
            description=description,
            readme_content=readme_content,
            main_module=main_module,
            functions=analyzer.functions,
            classes=analyzer.classes,
            dependencies=dependencies,
            entry_points=entry_points,
            examples_found=examples,
        )

    def _extract_repo_name(self, repo_path: Path) -> str:
        """Extract repository name from path or git config."""
        # Try to get from git remote
        try:
            git_config = repo_path / ".git" / "config"
            if git_config.exists():
                content = git_config.read_text()
                match = re.search(r"url = .*/([^/]+?)(?:\.git)?$", content, re.MULTILINE)
                if match:
                    return match.group(1)
        except Exception:
            pass

        # Fall back to directory name
        return repo_path.name

    def _find_and_read_readme(self, repo_path: Path) -> str | None:
        """Find and read the README file."""
        readme_patterns = ["README.md", "README.rst", "README.txt", "README"]
        for pattern in readme_patterns:
            readme_path = repo_path / pattern
            if readme_path.exists():
                try:
                    return readme_path.read_text(encoding="utf-8")
                except Exception:
                    pass
        return None

    def _extract_description(self, readme_content: str) -> str:
        """Extract description from README content."""
        # Get first paragraph after title
        lines = readme_content.split("\n")
        in_paragraph = False
        paragraph_lines: list[str] = []

        for line in lines:
            # Skip title lines
            if line.startswith("#"):
                in_paragraph = False
                paragraph_lines = []
                continue

            # Skip badges and links at the start
            if re.match(r"^\s*\[!\[", line) or re.match(r"^\s*\[.*\]\(", line):
                continue

            stripped = line.strip()
            if stripped:
                in_paragraph = True
                paragraph_lines.append(stripped)
            elif in_paragraph and paragraph_lines:
                # End of paragraph
                break

        description = " ".join(paragraph_lines)
        # Limit to reasonable length
        if len(description) > 500:
            description = description[:497] + "..."
        return description

    def _find_main_module(self, repo_path: Path) -> str | None:
        """Find the main module of the repository."""
        # Look for setup.py or pyproject.toml
        setup_py = repo_path / "setup.py"
        if setup_py.exists():
            try:
                content = setup_py.read_text()
                match = re.search(r"packages\s*=\s*\[['\"]([^'\"]+)['\"]", content)
                if match:
                    return match.group(1)
            except Exception:
                pass

        # Look for common patterns
        for pattern in ["src", "lib", "app"]:
            module_path = repo_path / pattern
            if module_path.is_dir():
                return pattern

        # Look for __init__.py in root
        init_files = list(repo_path.glob("*/__init__.py"))
        if init_files:
            return init_files[0].parent.name

        return None

    def _find_python_files(self, repo_path: Path, focus_paths: list[str]) -> list[Path]:
        """Find Python files to analyze."""
        python_files: list[Path] = []

        if focus_paths:
            for focus in focus_paths:
                focus_path = repo_path / focus
                if focus_path.exists():
                    python_files.extend(focus_path.rglob("*.py"))
        else:
            # Analyze all Python files, excluding tests and venv
            for py_file in repo_path.rglob("*.py"):
                rel_path = str(py_file.relative_to(repo_path))
                if not any(part in rel_path for part in ["test", "tests", "venv", ".venv", "env", ".tox"]):
                    python_files.append(py_file)

        return python_files

    def _extract_dependencies(self, repo_path: Path) -> list[str]:
        """Extract dependencies from requirements.txt or pyproject.toml."""
        dependencies: list[str] = []

        # Try requirements.txt
        req_file = repo_path / "requirements.txt"
        if req_file.exists():
            try:
                content = req_file.read_text()
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        # Extract just the package name
                        match = re.match(r"^([a-zA-Z0-9_-]+)", line)
                        if match:
                            dependencies.append(match.group(1))
            except Exception:
                pass

        # Try pyproject.toml
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                # Simple regex extraction
                deps_match = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
                if deps_match:
                    deps_str = deps_match.group(1)
                    for dep in re.findall(r'"([^"]+)"', deps_str):
                        match = re.match(r"^([a-zA-Z0-9_-]+)", dep)
                        if match:
                            dependencies.append(match.group(1))
            except Exception:
                pass

        return list(set(dependencies))

    def _find_entry_points(self, repo_path: Path) -> list[str]:
        """Find entry points (CLI commands, main functions)."""
        entry_points: list[str] = []

        # Look for __main__.py
        main_files = list(repo_path.rglob("__main__.py"))
        for f in main_files:
            entry_points.append(str(f.relative_to(repo_path)))

        # Look for cli.py or main.py
        for pattern in ["cli.py", "main.py", "app.py"]:
            for f in repo_path.rglob(pattern):
                entry_points.append(str(f.relative_to(repo_path)))

        return entry_points

    def _find_example_files(self, repo_path: Path) -> list[str]:
        """Find example files in the repository."""
        examples: list[str] = []

        # Look for examples directory
        for examples_dir in ["examples", "example", "demos", "demo"]:
            dir_path = repo_path / examples_dir
            if dir_path.is_dir():
                for f in dir_path.rglob("*.py"):
                    examples.append(str(f.relative_to(repo_path)))

        return examples

    def _extract_readme_info(self, readme_content: str) -> dict[str, Any]:
        """Extract structured information from README."""
        info: dict[str, Any] = {
            "title": None,
            "description": None,
            "installation": None,
            "usage": None,
            "features": [],
            "examples": [],
        }

        # Extract title
        title_match = re.search(r"^#\s+(.+)$", readme_content, re.MULTILINE)
        if title_match:
            info["title"] = title_match.group(1).strip()

        # Extract description
        info["description"] = self._extract_description(readme_content)

        # Extract installation section
        install_match = re.search(
            r"##\s+(?:Installation|Install|Getting Started)\s*\n(.*?)(?=\n##|\Z)",
            readme_content,
            re.IGNORECASE | re.DOTALL,
        )
        if install_match:
            info["installation"] = install_match.group(1).strip()[:1000]

        # Extract usage section
        usage_match = re.search(
            r"##\s+(?:Usage|Quick Start|Getting Started)\s*\n(.*?)(?=\n##|\Z)",
            readme_content,
            re.IGNORECASE | re.DOTALL,
        )
        if usage_match:
            info["usage"] = usage_match.group(1).strip()[:1000]

        # Extract features
        features_match = re.search(
            r"##\s+Features?\s*\n(.*?)(?=\n##|\Z)",
            readme_content,
            re.IGNORECASE | re.DOTALL,
        )
        if features_match:
            features_text = features_match.group(1)
            info["features"] = re.findall(r"[-*]\s+(.+?)(?:\n|$)", features_text)

        # Extract code examples
        code_blocks = re.findall(r"```(?:python|py)?\n(.*?)```", readme_content, re.DOTALL)
        info["examples"] = code_blocks[:5]  # Limit to 5 examples

        return info

    def _generate_skill_package(
        self,
        analysis: RepositoryAnalysis,
        skill_name: str,
        repo_url: str,
        include_examples: bool,
    ) -> SkillPackage:
        """Generate a skill package from repository analysis."""
        # Create feature categories from classes
        feature_categories: list[SkillFeatureCategory] = []
        if analysis.classes:
            api_features: list[SkillFeatureMapping] = []
            for cls in analysis.classes[:10]:  # Limit to top 10
                for method in cls.methods[:5]:  # Limit methods per class
                    if method.docstring:
                        api_features.append(
                            SkillFeatureMapping(
                                feature=f"{cls.name}.{method.name}",
                                user_value=method.docstring.split("\n")[0][:100],
                                when_to_use=f"When working with {cls.name}",
                            )
                        )
            if api_features:
                feature_categories.append(
                    SkillFeatureCategory(
                        category="Help Users「Use the API」",
                        mappings=api_features[:15],
                    )
                )

        # Create workflow steps
        workflow_steps = [
            SkillWorkflowStep(
                step_number=1,
                description="Analyze the task requirements",
                substeps=["Identify what functionality is needed", "Map to available API"],
            ),
            SkillWorkflowStep(
                step_number=2,
                description=f"Import and use {skill_name}",
                substeps=["Install dependencies if needed", "Import the required modules"],
            ),
            SkillWorkflowStep(
                step_number=3,
                description="Execute the operation",
                substeps=["Call the appropriate functions/methods", "Handle errors gracefully"],
            ),
        ]

        # Create examples from analysis
        examples: list[SkillExample] = []
        if include_examples and analysis.examples_found:
            for example_file in analysis.examples_found[:3]:
                examples.append(
                    SkillExample(
                        title=f"Example: {Path(example_file).stem}",
                        description=f"Example usage from {example_file}",
                    )
                )

        # Create metadata
        metadata = SkillPackageMetadata(
            name=skill_name,
            description=analysis.description or f"Skill package for {analysis.name}",
            version="1.0.0",
            category="custom",
            icon="github",
            required_tools=["code_execute_python", "shell_exec"],
            optional_tools=["file_write", "file_read"],
            goal=f"Enable the agent to use {analysis.name} effectively",
            core_principle="Leverage the repository's API to accomplish tasks efficiently",
            tags=["github", "external"],
            python_dependencies=analysis.dependencies,
            feature_categories=feature_categories,
            workflow_steps=workflow_steps,
            examples=examples,
        )

        # Generate reference file with API documentation
        api_doc = self._generate_api_documentation(analysis)
        references = [SkillPackageFile.from_content("api_reference.md", api_doc)]

        # Generate install script
        install_script = self._generate_install_script(repo_url, analysis)
        scripts = [SkillPackageFile.from_content("install.py", install_script)]

        return self._packager.create_package(
            metadata=metadata,
            scripts=scripts,
            references=references,
        )

    def _generate_api_documentation(self, analysis: RepositoryAnalysis) -> str:
        """Generate API documentation from analysis."""
        doc_parts = [f"# {analysis.name} API Reference\n"]

        if analysis.description:
            doc_parts.append(f"{analysis.description}\n")

        # Document classes
        if analysis.classes:
            doc_parts.append("\n## Classes\n")
            for cls in analysis.classes[:20]:
                doc_parts.append(f"\n### {cls.name}\n")
                if cls.docstring:
                    doc_parts.append(f"{cls.docstring}\n")
                if cls.base_classes:
                    doc_parts.append(f"**Inherits from:** {', '.join(cls.base_classes)}\n")

                if cls.methods:
                    doc_parts.append("\n**Methods:**\n")
                    for method in cls.methods:
                        params = ", ".join(f"{name}: {hint}" if hint else name for name, hint in method.parameters)
                        return_str = f" -> {method.return_type}" if method.return_type else ""
                        async_str = "async " if method.is_async else ""
                        doc_parts.append(f"- `{async_str}{method.name}({params}){return_str}`")
                        if method.docstring:
                            first_line = method.docstring.split("\n")[0]
                            doc_parts.append(f"  - {first_line}")
                        doc_parts.append("")

        # Document standalone functions
        standalone_funcs = [
            f
            for f in analysis.functions
            if not any(f.source_file == cls.source_file and f.line_number > cls.line_number for cls in analysis.classes)
        ]
        if standalone_funcs:
            doc_parts.append("\n## Functions\n")
            for func in standalone_funcs[:30]:
                params = ", ".join(f"{name}: {hint}" if hint else name for name, hint in func.parameters)
                return_str = f" -> {func.return_type}" if func.return_type else ""
                async_str = "async " if func.is_async else ""
                doc_parts.append(f"\n### `{async_str}{func.name}({params}){return_str}`\n")
                if func.docstring:
                    doc_parts.append(f"{func.docstring}\n")
                doc_parts.append(f"*Defined in {func.source_file}:{func.line_number}*\n")

        return "\n".join(doc_parts)

    def _generate_install_script(self, repo_url: str, analysis: RepositoryAnalysis) -> str:
        """Generate installation script."""
        deps_str = ", ".join(f'"{d}"' for d in analysis.dependencies)
        return f'''"""Installation script for {analysis.name}."""

import subprocess
import sys


def install():
    """Install the package and dependencies."""
    # Install from PyPI if available, otherwise from GitHub
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "{analysis.name}"
        ])
        print(f"Installed {analysis.name} from PyPI")
    except subprocess.CalledProcessError:
        # Fall back to GitHub installation
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            f"git+{repo_url}"
        ])
        print(f"Installed {analysis.name} from GitHub")

    # Install additional dependencies
    dependencies = [{deps_str}]
    for dep in dependencies:
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", dep
            ])
        except subprocess.CalledProcessError:
            print(f"Warning: Failed to install {{dep}}")


if __name__ == "__main__":
    install()
'''

    def _format_discovery_result(self, package: SkillPackage, analysis: RepositoryAnalysis) -> str:
        """Format the discovery result for display."""
        parts = [
            f"# Skill Package: {package.name}\n",
            f"**Description:** {package.description}\n",
            f"**Package Type:** {package.package_type.value}\n",
            f"**Version:** {package.version}\n",
            "\n## Analysis Summary\n",
            f"- **Functions discovered:** {len(analysis.functions)}",
            f"- **Classes discovered:** {len(analysis.classes)}",
            f"- **Dependencies:** {len(analysis.dependencies)}",
            f"- **Entry points:** {len(analysis.entry_points)}",
            f"- **Example files found:** {len(analysis.examples_found)}",
            "\n## Package Contents\n",
            f"- **Total files:** {package.file_count}",
            f"- **Total size:** {package.total_size} bytes",
        ]

        if package.has_scripts:
            parts.append("- Scripts: Yes")
        if package.has_references:
            parts.append("- API Reference: Yes")

        if analysis.dependencies:
            parts.append("\n## Dependencies\n")
            for dep in analysis.dependencies[:10]:
                parts.append(f"- {dep}")
            if len(analysis.dependencies) > 10:
                parts.append(f"- ... and {len(analysis.dependencies) - 10} more")

        parts.append(
            "\n\nThe skill package has been created and is ready for use. "
            "You can now deploy this skill to enhance the agent's capabilities."
        )

        return "\n".join(parts)

    def _format_readme_analysis(self, info: dict[str, Any]) -> str:
        """Format README analysis for display."""
        parts = []

        if info.get("title"):
            parts.append(f"# {info['title']}\n")

        if info.get("description"):
            parts.append(f"**Description:** {info['description']}\n")

        if info.get("features"):
            parts.append("\n## Features\n")
            for feature in info["features"][:10]:
                parts.append(f"- {feature}")

        if info.get("installation"):
            parts.append("\n## Installation\n")
            parts.append(info["installation"][:500])

        if info.get("usage"):
            parts.append("\n## Usage\n")
            parts.append(info["usage"][:500])

        if info.get("examples"):
            parts.append(f"\n## Code Examples ({len(info['examples'])} found)\n")
            if info["examples"]:
                parts.append("```python")
                parts.append(info["examples"][0][:300])
                parts.append("```")

        return "\n".join(parts)
