"""Tests for GitHubSkillSeeker tool and its supporting classes."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.tools.github_skill_seeker import (
    ExtractedClass,
    ExtractedFunction,
    GitHubSkillSeeker,
    PythonASTAnalyzer,
    RepositoryAnalysis,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extracted_function(
    name: str = "do_work",
    docstring: str | None = "Do some work.",
    parameters: list[tuple[str, str | None]] | None = None,
    return_type: str | None = None,
    is_async: bool = False,
    decorators: list[str] | None = None,
    line_number: int = 1,
    source_file: str = "module.py",
) -> ExtractedFunction:
    return ExtractedFunction(
        name=name,
        docstring=docstring,
        parameters=parameters or [],
        return_type=return_type,
        is_async=is_async,
        decorators=decorators or [],
        line_number=line_number,
        source_file=source_file,
    )


def _make_extracted_class(
    name: str = "MyClass",
    docstring: str | None = "A class.",
    methods: list[ExtractedFunction] | None = None,
    base_classes: list[str] | None = None,
    decorators: list[str] | None = None,
    line_number: int = 10,
    source_file: str = "module.py",
) -> ExtractedClass:
    return ExtractedClass(
        name=name,
        docstring=docstring,
        methods=methods or [],
        base_classes=base_classes or [],
        decorators=decorators or [],
        line_number=line_number,
        source_file=source_file,
    )


def _make_analysis(
    name: str = "my_repo",
    description: str = "A test repo",
    readme_content: str | None = "# My Repo\n\nA test repo.",
    main_module: str | None = "mymodule",
    functions: list[ExtractedFunction] | None = None,
    classes: list[ExtractedClass] | None = None,
    dependencies: list[str] | None = None,
    entry_points: list[str] | None = None,
    examples_found: list[str] | None = None,
) -> RepositoryAnalysis:
    return RepositoryAnalysis(
        name=name,
        description=description,
        readme_content=readme_content,
        main_module=main_module,
        functions=functions or [],
        classes=classes or [],
        dependencies=dependencies or [],
        entry_points=entry_points or [],
        examples_found=examples_found or [],
    )


def _make_skill_package_mock(
    name: str = "my_repo",
    description: str = "A skill",
    package_type_value: str = "standard",
    version: str = "1.0.0",
    file_count: int = 2,
    total_size: int = 512,
    has_scripts: bool = True,
    has_references: bool = True,
) -> MagicMock:
    pkg = MagicMock()
    pkg.name = name
    pkg.description = description
    pkg.version = version
    pkg.file_count = file_count
    pkg.total_size = total_size
    pkg.has_scripts = has_scripts
    pkg.has_references = has_references
    pkg.summary = {
        "id": "test-id",
        "name": name,
        "description": description,
        "version": version,
        "package_type": package_type_value,
        "file_count": file_count,
        "total_size": total_size,
    }
    pkg.package_type = MagicMock()
    pkg.package_type.value = package_type_value
    return pkg


def _make_seeker() -> GitHubSkillSeeker:
    """Return a GitHubSkillSeeker with a mocked packager."""
    with patch("app.domain.services.tools.github_skill_seeker.get_skill_packager") as mock_factory:
        mock_factory.return_value = MagicMock()
        return GitHubSkillSeeker()


# ---------------------------------------------------------------------------
# ExtractedFunction dataclass
# ---------------------------------------------------------------------------


class TestExtractedFunction:
    """Tests for the ExtractedFunction dataclass."""

    def test_basic_construction(self) -> None:
        func = _make_extracted_function()
        assert func.name == "do_work"
        assert func.docstring == "Do some work."
        assert func.parameters == []
        assert func.return_type is None
        assert func.is_async is False
        assert func.decorators == []
        assert func.line_number == 1
        assert func.source_file == "module.py"

    def test_async_function(self) -> None:
        func = _make_extracted_function(name="fetch", is_async=True)
        assert func.is_async is True

    def test_function_with_parameters(self) -> None:
        params = [("x", "int"), ("y", None), ("z", "str")]
        func = _make_extracted_function(parameters=params)
        assert func.parameters == params

    def test_function_with_return_type(self) -> None:
        func = _make_extracted_function(return_type="list[str]")
        assert func.return_type == "list[str]"

    def test_function_with_decorators(self) -> None:
        func = _make_extracted_function(decorators=["staticmethod", "cache"])
        assert func.decorators == ["staticmethod", "cache"]

    def test_function_no_docstring(self) -> None:
        func = _make_extracted_function(docstring=None)
        assert func.docstring is None


# ---------------------------------------------------------------------------
# ExtractedClass dataclass
# ---------------------------------------------------------------------------


class TestExtractedClass:
    """Tests for the ExtractedClass dataclass."""

    def test_basic_construction(self) -> None:
        cls = _make_extracted_class()
        assert cls.name == "MyClass"
        assert cls.docstring == "A class."
        assert cls.methods == []
        assert cls.base_classes == []
        assert cls.decorators == []
        assert cls.line_number == 10
        assert cls.source_file == "module.py"

    def test_class_with_methods(self) -> None:
        method = _make_extracted_function(name="compute")
        cls = _make_extracted_class(methods=[method])
        assert len(cls.methods) == 1
        assert cls.methods[0].name == "compute"

    def test_class_with_base_classes(self) -> None:
        cls = _make_extracted_class(base_classes=["BaseModel", "Protocol"])
        assert cls.base_classes == ["BaseModel", "Protocol"]

    def test_class_with_decorators(self) -> None:
        cls = _make_extracted_class(decorators=["dataclass"])
        assert cls.decorators == ["dataclass"]

    def test_class_no_docstring(self) -> None:
        cls = _make_extracted_class(docstring=None)
        assert cls.docstring is None


# ---------------------------------------------------------------------------
# RepositoryAnalysis dataclass
# ---------------------------------------------------------------------------


class TestRepositoryAnalysis:
    """Tests for the RepositoryAnalysis dataclass."""

    def test_default_field_factories(self) -> None:
        analysis = RepositoryAnalysis(
            name="repo",
            description="desc",
            readme_content=None,
            main_module=None,
        )
        assert analysis.functions == []
        assert analysis.classes == []
        assert analysis.dependencies == []
        assert analysis.entry_points == []
        assert analysis.examples_found == []

    def test_full_construction(self) -> None:
        func = _make_extracted_function()
        cls = _make_extracted_class()
        analysis = _make_analysis(
            functions=[func],
            classes=[cls],
            dependencies=["requests", "pydantic"],
            entry_points=["cli.py"],
            examples_found=["examples/demo.py"],
        )
        assert len(analysis.functions) == 1
        assert len(analysis.classes) == 1
        assert analysis.dependencies == ["requests", "pydantic"]
        assert analysis.entry_points == ["cli.py"]
        assert analysis.examples_found == ["examples/demo.py"]

    def test_null_readme_and_module(self) -> None:
        analysis = _make_analysis(readme_content=None, main_module=None)
        assert analysis.readme_content is None
        assert analysis.main_module is None


# ---------------------------------------------------------------------------
# PythonASTAnalyzer
# ---------------------------------------------------------------------------


class TestPythonASTAnalyzer:
    """Tests for PythonASTAnalyzer."""

    def test_initial_state_is_empty(self) -> None:
        analyzer = PythonASTAnalyzer()
        assert analyzer.functions == []
        assert analyzer.classes == []

    # --- analyze_file ---

    def test_analyze_file_extracts_public_function(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            '''\
            def greet(name: str) -> str:
                """Return greeting."""
                return f"Hello, {name}"
            '''
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        assert len(analyzer.functions) == 1
        assert analyzer.functions[0].name == "greet"
        assert analyzer.functions[0].docstring == "Return greeting."
        assert analyzer.functions[0].parameters == [("name", "str")]
        assert analyzer.functions[0].return_type == "str"
        assert analyzer.functions[0].is_async is False
        assert analyzer.functions[0].source_file == "mod.py"

    def test_analyze_file_skips_private_functions(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            """\
            def _helper():
                pass

            def public_fn():
                pass
            """
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        names = [f.name for f in analyzer.functions]
        assert "public_fn" in names
        assert "_helper" not in names

    def test_analyze_file_extracts_async_function(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            '''\
            async def fetch(url: str) -> bytes:
                """Fetch URL."""
                ...
            '''
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        assert len(analyzer.functions) == 1
        assert analyzer.functions[0].is_async is True

    def test_analyze_file_extracts_public_class(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            '''\
            class Manager:
                """Manages things."""

                def run(self) -> None:
                    """Run it."""
                    ...
            '''
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        assert len(analyzer.classes) == 1
        cls = analyzer.classes[0]
        assert cls.name == "Manager"
        assert cls.docstring == "Manages things."
        assert len(cls.methods) == 1
        assert cls.methods[0].name == "run"

    def test_analyze_file_skips_private_classes(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            """\
            class _Internal:
                pass

            class Public:
                pass
            """
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        names = [c.name for c in analyzer.classes]
        assert "Public" in names
        assert "_Internal" not in names

    def test_analyze_file_class_includes_init(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            '''\
            class Widget:
                def __init__(self, value: int) -> None:
                    """Set up widget."""
                    self.value = value
            '''
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        assert len(analyzer.classes) == 1
        method_names = [m.name for m in analyzer.classes[0].methods]
        assert "__init__" in method_names

    def test_analyze_file_class_excludes_private_methods_except_init(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            """\
            class Service:
                def public_method(self) -> None:
                    pass

                def _private_method(self) -> None:
                    pass

                def __init__(self) -> None:
                    pass
            """
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        method_names = [m.name for m in analyzer.classes[0].methods]
        assert "public_method" in method_names
        assert "__init__" in method_names
        assert "_private_method" not in method_names

    def test_analyze_file_skips_syntax_errors_silently(self, tmp_path: Path) -> None:
        py_file = tmp_path / "bad.py"
        py_file.write_text("def broken(:\n    pass\n", encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "bad.py")
        assert analyzer.functions == []
        assert analyzer.classes == []

    def test_analyze_file_skips_unicode_decode_errors(self, tmp_path: Path) -> None:
        py_file = tmp_path / "binary.py"
        py_file.write_bytes(b"\xff\xfe invalid utf-8 bytes")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "binary.py")
        assert analyzer.functions == []

    def test_analyze_file_accumulates_across_calls(self, tmp_path: Path) -> None:
        src_a = "def func_a(): pass\n"
        src_b = "def func_b(): pass\n"
        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(src_a, encoding="utf-8")
        file_b.write_text(src_b, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(file_a, "a.py")
        analyzer.analyze_file(file_b, "b.py")
        names = [f.name for f in analyzer.functions]
        assert "func_a" in names
        assert "func_b" in names

    def test_analyze_file_extracts_function_without_docstring(self, tmp_path: Path) -> None:
        py_file = tmp_path / "mod.py"
        py_file.write_text("def no_doc(): pass\n", encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        assert analyzer.functions[0].docstring is None

    def test_analyze_file_extracts_function_decorators(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            """\
            import functools

            @functools.cache
            def cached_fn(x: int) -> int:
                return x
            """
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        assert any("cache" in d for d in analyzer.functions[0].decorators)

    def test_analyze_file_method_drops_self_parameter(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            '''\
            class Calc:
                def add(self, a: int, b: int) -> int:
                    """Add two numbers."""
                    return a + b
            '''
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        method = analyzer.classes[0].methods[0]
        param_names = [p[0] for p in method.parameters]
        assert "self" not in param_names
        assert "a" in param_names
        assert "b" in param_names

    def test_analyze_file_class_base_classes(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            """\
            class MyService(BaseService, Mixin):
                pass
            """
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        assert "BaseService" in analyzer.classes[0].base_classes
        assert "Mixin" in analyzer.classes[0].base_classes

    def test_analyze_file_function_without_type_hints(self, tmp_path: Path) -> None:
        py_file = tmp_path / "mod.py"
        py_file.write_text("def raw(x, y): pass\n", encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        func = analyzer.functions[0]
        assert func.parameters == [("x", None), ("y", None)]
        assert func.return_type is None

    def test_analyze_file_records_line_number(self, tmp_path: Path) -> None:
        src = "# comment\n\ndef delayed(): pass\n"
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        assert analyzer.functions[0].line_number == 3

    def test_analyze_file_class_call_method_included(self, tmp_path: Path) -> None:
        src = textwrap.dedent(
            '''\
            class Pipeline:
                def __call__(self, data):
                    """Run pipeline."""
                    return data
            '''
        )
        py_file = tmp_path / "mod.py"
        py_file.write_text(src, encoding="utf-8")
        analyzer = PythonASTAnalyzer()
        analyzer.analyze_file(py_file, "mod.py")
        method_names = [m.name for m in analyzer.classes[0].methods]
        assert "__call__" in method_names


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._normalize_repo_url
# ---------------------------------------------------------------------------


class TestNormalizeRepoUrl:
    """Tests for _normalize_repo_url."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_owner_repo_shorthand(self) -> None:
        result = self.seeker._normalize_repo_url("owner/my-repo")
        assert result == "https://github.com/owner/my-repo"

    def test_full_https_url_unchanged(self) -> None:
        url = "https://github.com/owner/repo"
        assert self.seeker._normalize_repo_url(url) == url

    def test_removes_dot_git_suffix(self) -> None:
        url = "https://github.com/owner/repo.git"
        assert self.seeker._normalize_repo_url(url) == "https://github.com/owner/repo"

    def test_converts_ssh_to_https(self) -> None:
        url = "git@github.com:owner/repo"
        result = self.seeker._normalize_repo_url(url)
        assert result == "https://github.com/owner/repo"

    def test_ssh_with_git_suffix(self) -> None:
        url = "git@github.com:owner/repo.git"
        result = self.seeker._normalize_repo_url(url)
        assert result == "https://github.com/owner/repo"

    def test_strips_leading_trailing_whitespace(self) -> None:
        result = self.seeker._normalize_repo_url("  owner/repo  ")
        assert result == "https://github.com/owner/repo"

    def test_full_url_with_github_dot_com_not_duplicated(self) -> None:
        url = "https://github.com/user/project"
        result = self.seeker._normalize_repo_url(url)
        assert result.count("github.com") == 1

    def test_owner_repo_with_hyphen_and_underscore(self) -> None:
        result = self.seeker._normalize_repo_url("my-org/my_project")
        assert result == "https://github.com/my-org/my_project"


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._extract_description
# ---------------------------------------------------------------------------


class TestExtractDescription:
    """Tests for _extract_description."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_extracts_first_paragraph(self) -> None:
        readme = "# Title\n\nThis is the description.\n\n## Section"
        desc = self.seeker._extract_description(readme)
        assert desc == "This is the description."

    def test_skips_title_line(self) -> None:
        readme = "# My Project\n\nActual description here."
        desc = self.seeker._extract_description(readme)
        assert "My Project" not in desc
        assert "Actual description here" in desc

    def test_stops_at_blank_line_after_paragraph(self) -> None:
        readme = "# Title\n\nLine one.\nLine two.\n\nSecond paragraph."
        desc = self.seeker._extract_description(readme)
        assert "Line one" in desc
        assert "Line two" in desc
        assert "Second paragraph" not in desc

    def test_skips_badge_lines(self) -> None:
        readme = "# Title\n\n[![Build](img)](link)\n\nReal description."
        desc = self.seeker._extract_description(readme)
        assert desc == "Real description."

    def test_truncates_long_description(self) -> None:
        readme = "# Title\n\n" + "x" * 600
        desc = self.seeker._extract_description(readme)
        assert len(desc) <= 500
        assert desc.endswith("...")

    def test_empty_readme_returns_empty_string(self) -> None:
        desc = self.seeker._extract_description("")
        assert desc == ""

    def test_readme_with_only_title(self) -> None:
        desc = self.seeker._extract_description("# Just a Title\n")
        assert desc == ""

    def test_multiline_paragraph_joined_with_spaces(self) -> None:
        readme = "# T\n\nFirst line\nSecond line\nThird line\n\n## Next"
        desc = self.seeker._extract_description(readme)
        assert desc == "First line Second line Third line"


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._find_and_read_readme
# ---------------------------------------------------------------------------


class TestFindAndReadReadme:
    """Tests for _find_and_read_readme."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_finds_readme_md(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")
        result = self.seeker._find_and_read_readme(tmp_path)
        assert result == "# Hello"

    def test_finds_readme_rst(self, tmp_path: Path) -> None:
        (tmp_path / "README.rst").write_text("Rst content", encoding="utf-8")
        result = self.seeker._find_and_read_readme(tmp_path)
        assert result == "Rst content"

    def test_finds_readme_txt(self, tmp_path: Path) -> None:
        (tmp_path / "README.txt").write_text("Plain text", encoding="utf-8")
        result = self.seeker._find_and_read_readme(tmp_path)
        assert result == "Plain text"

    def test_finds_readme_no_extension(self, tmp_path: Path) -> None:
        (tmp_path / "README").write_text("Bare readme", encoding="utf-8")
        result = self.seeker._find_and_read_readme(tmp_path)
        assert result == "Bare readme"

    def test_prefers_readme_md_over_rst(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("md content", encoding="utf-8")
        (tmp_path / "README.rst").write_text("rst content", encoding="utf-8")
        result = self.seeker._find_and_read_readme(tmp_path)
        assert result == "md content"

    def test_returns_none_when_no_readme(self, tmp_path: Path) -> None:
        result = self.seeker._find_and_read_readme(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._extract_readme_info
# ---------------------------------------------------------------------------


class TestExtractReadmeInfo:
    """Tests for _extract_readme_info."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_extracts_title(self) -> None:
        readme = "# My Library\n\nDescription here."
        info = self.seeker._extract_readme_info(readme)
        assert info["title"] == "My Library"

    def test_extracts_description(self) -> None:
        readme = "# Title\n\nThis library does things."
        info = self.seeker._extract_readme_info(readme)
        assert "This library does things" in info["description"]

    def test_extracts_installation_section(self) -> None:
        readme = "# T\n\n## Installation\n\npip install mylib\n\n## Usage\n\nuse it"
        info = self.seeker._extract_readme_info(readme)
        assert info["installation"] is not None
        assert "pip install" in info["installation"]

    def test_extracts_usage_section(self) -> None:
        readme = "# T\n\n## Usage\n\nimport mylib\nmylib.run()\n\n## More"
        info = self.seeker._extract_readme_info(readme)
        assert info["usage"] is not None
        assert "import mylib" in info["usage"]

    def test_extracts_features_list(self) -> None:
        readme = "# T\n\n## Features\n\n- Fast\n- Lightweight\n- Easy\n\n## End"
        info = self.seeker._extract_readme_info(readme)
        assert "Fast" in info["features"]
        assert "Lightweight" in info["features"]

    def test_extracts_code_examples(self) -> None:
        readme = "# T\n\n```python\nimport foo\nfoo.bar()\n```"
        info = self.seeker._extract_readme_info(readme)
        assert len(info["examples"]) == 1
        assert "import foo" in info["examples"][0]

    def test_limits_code_examples_to_five(self) -> None:
        code_block = "```python\nprint('hello')\n```\n\n"
        readme = "# T\n\n" + code_block * 10
        info = self.seeker._extract_readme_info(readme)
        assert len(info["examples"]) <= 5

    def test_defaults_when_no_sections(self) -> None:
        readme = "Nothing useful"
        info = self.seeker._extract_readme_info(readme)
        assert info["title"] is None
        assert info["installation"] is None
        assert info["usage"] is None
        assert info["features"] == []

    def test_case_insensitive_installation_header(self) -> None:
        readme = "# T\n\n## install\n\npip install x\n\n## End"
        info = self.seeker._extract_readme_info(readme)
        assert info["installation"] is not None

    def test_installation_truncated_to_1000_chars(self) -> None:
        long_install = "pip install " + "x" * 2000
        readme = f"# T\n\n## Installation\n\n{long_install}\n\n## End"
        info = self.seeker._extract_readme_info(readme)
        assert len(info["installation"]) <= 1000


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._extract_repo_name
# ---------------------------------------------------------------------------


class TestExtractRepoName:
    """Tests for _extract_repo_name."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_falls_back_to_directory_name(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "my-project"
        repo_dir.mkdir()
        name = self.seeker._extract_repo_name(repo_dir)
        assert name == "my-project"

    def test_extracts_name_from_git_config(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text('[remote "origin"]\n\turl = https://github.com/owner/awesome-lib.git\n')
        name = self.seeker._extract_repo_name(tmp_path)
        assert name == "awesome-lib"

    def test_falls_back_when_git_config_has_no_url(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0\n")
        name = self.seeker._extract_repo_name(tmp_path)
        assert name == tmp_path.name


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._find_main_module
# ---------------------------------------------------------------------------


class TestFindMainModule:
    """Tests for _find_main_module."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        result = self.seeker._find_main_module(tmp_path)
        assert result is None

    def test_finds_src_directory(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        result = self.seeker._find_main_module(tmp_path)
        assert result == "src"

    def test_finds_lib_directory(self, tmp_path: Path) -> None:
        (tmp_path / "lib").mkdir()
        result = self.seeker._find_main_module(tmp_path)
        assert result == "lib"

    def test_finds_app_directory(self, tmp_path: Path) -> None:
        (tmp_path / "app").mkdir()
        result = self.seeker._find_main_module(tmp_path)
        assert result == "app"

    def test_extracts_from_setup_py(self, tmp_path: Path) -> None:
        setup = tmp_path / "setup.py"
        setup.write_text('packages=["mypackage"]\n')
        result = self.seeker._find_main_module(tmp_path)
        assert result == "mypackage"

    def test_finds_init_py_in_subdirectory(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "mymodule"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        result = self.seeker._find_main_module(tmp_path)
        assert result == "mymodule"


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._find_python_files
# ---------------------------------------------------------------------------


class TestFindPythonFiles:
    """Tests for _find_python_files."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_returns_empty_when_no_py_files(self, tmp_path: Path) -> None:
        result = self.seeker._find_python_files(tmp_path, [])
        assert result == []

    def test_finds_py_files_recursively(self, tmp_path: Path) -> None:
        subdir = tmp_path / "pkg"
        subdir.mkdir()
        (tmp_path / "main.py").write_text("")
        (subdir / "helper.py").write_text("")
        result = self.seeker._find_python_files(tmp_path, [])
        paths = [str(p) for p in result]
        assert any("main.py" in p for p in paths)
        assert any("helper.py" in p for p in paths)

    def test_excludes_test_directories(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_something.py").write_text("")
        (tmp_path / "main.py").write_text("")
        result = self.seeker._find_python_files(tmp_path, [])
        assert not any("test_something" in str(p) for p in result)

    def test_excludes_venv_directories(self, tmp_path: Path) -> None:
        venv_dir = tmp_path / "venv"
        venv_dir.mkdir()
        (venv_dir / "site.py").write_text("")
        result = self.seeker._find_python_files(tmp_path, [])
        assert not any("venv" in str(p) for p in result)

    def test_excludes_dot_venv_directory(self, tmp_path: Path) -> None:
        dot_venv = tmp_path / ".venv"
        dot_venv.mkdir()
        (dot_venv / "bin.py").write_text("")
        result = self.seeker._find_python_files(tmp_path, [])
        assert not any(".venv" in str(p) for p in result)

    def test_excludes_tox_directory(self, tmp_path: Path) -> None:
        tox_dir = tmp_path / ".tox"
        tox_dir.mkdir()
        (tox_dir / "run.py").write_text("")
        result = self.seeker._find_python_files(tmp_path, [])
        assert all(".tox" not in str(p) for p in result)

    def test_respects_focus_paths(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        (src / "code.py").write_text("")
        (other / "excluded.py").write_text("")
        result = self.seeker._find_python_files(tmp_path, ["src"])
        assert any("code.py" in str(p) for p in result)
        assert not any("excluded.py" in str(p) for p in result)

    def test_focus_path_that_does_not_exist_returns_empty(self, tmp_path: Path) -> None:
        result = self.seeker._find_python_files(tmp_path, ["nonexistent"])
        assert result == []


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._extract_dependencies
# ---------------------------------------------------------------------------


class TestExtractDependencies:
    """Tests for _extract_dependencies."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_returns_empty_when_no_files(self, tmp_path: Path) -> None:
        result = self.seeker._extract_dependencies(tmp_path)
        assert result == []

    def test_parses_requirements_txt(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("requests==2.31.0\npydantic>=2.0\nhttpx\n")
        result = self.seeker._extract_dependencies(tmp_path)
        assert "requests" in result
        assert "pydantic" in result
        assert "httpx" in result

    def test_skips_comment_lines_in_requirements(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("# comment\nrequests\n")
        result = self.seeker._extract_dependencies(tmp_path)
        assert "requests" in result

    def test_skips_option_lines_in_requirements(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("-r base.txt\nflask\n")
        result = self.seeker._extract_dependencies(tmp_path)
        assert "flask" in result

    def test_parses_pyproject_toml_dependencies(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = [\n    "httpx>=0.24",\n    "pydantic>=2.0",\n]\n'
        )
        result = self.seeker._extract_dependencies(tmp_path)
        assert "httpx" in result
        assert "pydantic" in result

    def test_deduplicates_dependencies(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("requests\nrequests\n")
        result = self.seeker._extract_dependencies(tmp_path)
        assert result.count("requests") == 1

    def test_returns_list_type(self, tmp_path: Path) -> None:
        result = self.seeker._extract_dependencies(tmp_path)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._find_entry_points
# ---------------------------------------------------------------------------


class TestFindEntryPoints:
    """Tests for _find_entry_points."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_returns_empty_for_empty_repo(self, tmp_path: Path) -> None:
        result = self.seeker._find_entry_points(tmp_path)
        assert result == []

    def test_finds_main_py(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("")
        result = self.seeker._find_entry_points(tmp_path)
        assert any("main.py" in ep for ep in result)

    def test_finds_cli_py(self, tmp_path: Path) -> None:
        (tmp_path / "cli.py").write_text("")
        result = self.seeker._find_entry_points(tmp_path)
        assert any("cli.py" in ep for ep in result)

    def test_finds_app_py(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("")
        result = self.seeker._find_entry_points(tmp_path)
        assert any("app.py" in ep for ep in result)

    def test_finds_dunder_main(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__main__.py").write_text("")
        result = self.seeker._find_entry_points(tmp_path)
        assert any("__main__.py" in ep for ep in result)

    def test_returns_relative_paths(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "main.py").write_text("")
        result = self.seeker._find_entry_points(tmp_path)
        assert all(not Path(ep).is_absolute() for ep in result)


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._find_example_files
# ---------------------------------------------------------------------------


class TestFindExampleFiles:
    """Tests for _find_example_files."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_returns_empty_when_no_example_dirs(self, tmp_path: Path) -> None:
        result = self.seeker._find_example_files(tmp_path)
        assert result == []

    def test_finds_files_in_examples_dir(self, tmp_path: Path) -> None:
        examples = tmp_path / "examples"
        examples.mkdir()
        (examples / "demo.py").write_text("")
        result = self.seeker._find_example_files(tmp_path)
        assert any("demo.py" in p for p in result)

    def test_finds_files_in_demo_dir(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        demo.mkdir()
        (demo / "run.py").write_text("")
        result = self.seeker._find_example_files(tmp_path)
        assert any("run.py" in p for p in result)

    def test_finds_files_in_demos_dir(self, tmp_path: Path) -> None:
        demos = tmp_path / "demos"
        demos.mkdir()
        (demos / "show.py").write_text("")
        result = self.seeker._find_example_files(tmp_path)
        assert any("show.py" in p for p in result)

    def test_finds_files_in_example_singular_dir(self, tmp_path: Path) -> None:
        example = tmp_path / "example"
        example.mkdir()
        (example / "basic.py").write_text("")
        result = self.seeker._find_example_files(tmp_path)
        assert any("basic.py" in p for p in result)

    def test_only_returns_py_files(self, tmp_path: Path) -> None:
        examples = tmp_path / "examples"
        examples.mkdir()
        (examples / "demo.py").write_text("")
        (examples / "README.md").write_text("")
        result = self.seeker._find_example_files(tmp_path)
        assert all(p.endswith(".py") for p in result)


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._generate_api_documentation
# ---------------------------------------------------------------------------


class TestGenerateApiDocumentation:
    """Tests for _generate_api_documentation."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_includes_repo_name_in_header(self) -> None:
        analysis = _make_analysis(name="mylib")
        doc = self.seeker._generate_api_documentation(analysis)
        assert "mylib" in doc

    def test_includes_description_when_present(self) -> None:
        analysis = _make_analysis(description="Does amazing things.")
        doc = self.seeker._generate_api_documentation(analysis)
        assert "Does amazing things." in doc

    def test_documents_classes(self) -> None:
        cls = _make_extracted_class(name="Processor", docstring="Processes data.")
        analysis = _make_analysis(classes=[cls])
        doc = self.seeker._generate_api_documentation(analysis)
        assert "Processor" in doc
        assert "Processes data." in doc

    def test_documents_class_base_classes(self) -> None:
        cls = _make_extracted_class(name="MyModel", base_classes=["BaseModel"])
        analysis = _make_analysis(classes=[cls])
        doc = self.seeker._generate_api_documentation(analysis)
        assert "BaseModel" in doc

    def test_documents_class_methods(self) -> None:
        method = _make_extracted_function(
            name="process",
            docstring="Process the input.",
            parameters=[("data", "str")],
            return_type="str",
            is_async=True,
        )
        cls = _make_extracted_class(name="Worker", methods=[method])
        analysis = _make_analysis(classes=[cls])
        doc = self.seeker._generate_api_documentation(analysis)
        assert "process" in doc
        assert "async" in doc

    def test_documents_standalone_functions(self) -> None:
        func = _make_extracted_function(
            name="transform",
            docstring="Transform data.",
            line_number=1,
            source_file="utils.py",
        )
        analysis = _make_analysis(functions=[func])
        doc = self.seeker._generate_api_documentation(analysis)
        assert "transform" in doc
        assert "Transform data." in doc

    def test_limits_classes_to_20(self) -> None:
        classes = [_make_extracted_class(name=f"Cls{i}") for i in range(25)]
        analysis = _make_analysis(classes=classes)
        doc = self.seeker._generate_api_documentation(analysis)
        assert "Cls19" in doc
        assert "Cls24" not in doc

    def test_returns_string(self) -> None:
        analysis = _make_analysis()
        doc = self.seeker._generate_api_documentation(analysis)
        assert isinstance(doc, str)

    def test_async_prefix_on_method(self) -> None:
        method = _make_extracted_function(name="afetch", is_async=True)
        cls = _make_extracted_class(methods=[method])
        analysis = _make_analysis(classes=[cls])
        doc = self.seeker._generate_api_documentation(analysis)
        assert "async afetch" in doc


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._generate_install_script
# ---------------------------------------------------------------------------


class TestGenerateInstallScript:
    """Tests for _generate_install_script."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_returns_string(self) -> None:
        analysis = _make_analysis(name="mylib", dependencies=[])
        result = self.seeker._generate_install_script("https://github.com/o/mylib", analysis)
        assert isinstance(result, str)

    def test_contains_install_function(self) -> None:
        analysis = _make_analysis()
        script = self.seeker._generate_install_script("https://github.com/o/r", analysis)
        assert "def install():" in script

    def test_contains_repo_url(self) -> None:
        url = "https://github.com/owner/repo"
        analysis = _make_analysis()
        script = self.seeker._generate_install_script(url, analysis)
        assert url in script

    def test_contains_dependencies(self) -> None:
        analysis = _make_analysis(dependencies=["requests", "pydantic"])
        script = self.seeker._generate_install_script("https://github.com/o/r", analysis)
        assert "requests" in script
        assert "pydantic" in script

    def test_valid_python_syntax(self) -> None:
        analysis = _make_analysis(dependencies=["httpx"])
        script = self.seeker._generate_install_script("https://github.com/o/r", analysis)
        # Should not raise
        ast.parse(script)

    def test_no_dependencies_generates_empty_list(self) -> None:
        analysis = _make_analysis(dependencies=[])
        script = self.seeker._generate_install_script("https://github.com/o/r", analysis)
        assert "dependencies = []" in script


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._format_discovery_result
# ---------------------------------------------------------------------------


class TestFormatDiscoveryResult:
    """Tests for _format_discovery_result."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_includes_package_name(self) -> None:
        pkg = _make_skill_package_mock(name="awesome_skill")
        analysis = _make_analysis()
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert "awesome_skill" in result

    def test_includes_function_count(self) -> None:
        pkg = _make_skill_package_mock()
        funcs = [_make_extracted_function(name=f"fn{i}") for i in range(3)]
        analysis = _make_analysis(functions=funcs)
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert "3" in result

    def test_includes_class_count(self) -> None:
        pkg = _make_skill_package_mock()
        classes = [_make_extracted_class(name=f"C{i}") for i in range(2)]
        analysis = _make_analysis(classes=classes)
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert "2" in result

    def test_includes_dependency_list(self) -> None:
        pkg = _make_skill_package_mock()
        analysis = _make_analysis(dependencies=["requests", "pydantic"])
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert "requests" in result
        assert "pydantic" in result

    def test_truncates_dependency_list_at_10(self) -> None:
        pkg = _make_skill_package_mock()
        deps = [f"dep{i}" for i in range(15)]
        analysis = _make_analysis(dependencies=deps)
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert "5 more" in result

    def test_includes_scripts_note_when_present(self) -> None:
        pkg = _make_skill_package_mock(has_scripts=True)
        analysis = _make_analysis()
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert "Scripts" in result

    def test_includes_references_note_when_present(self) -> None:
        pkg = _make_skill_package_mock(has_references=True)
        analysis = _make_analysis()
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert "API Reference" in result

    def test_returns_string(self) -> None:
        pkg = _make_skill_package_mock()
        analysis = _make_analysis()
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert isinstance(result, str)

    def test_ends_with_deployment_message(self) -> None:
        pkg = _make_skill_package_mock()
        analysis = _make_analysis()
        result = self.seeker._format_discovery_result(pkg, analysis)
        assert "skill package" in result.lower()


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._format_readme_analysis
# ---------------------------------------------------------------------------


class TestFormatReadmeAnalysis:
    """Tests for _format_readme_analysis."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_includes_title_when_present(self) -> None:
        info = {
            "title": "My Lib",
            "description": None,
            "features": [],
            "installation": None,
            "usage": None,
            "examples": [],
        }
        result = self.seeker._format_readme_analysis(info)
        assert "My Lib" in result

    def test_includes_description_when_present(self) -> None:
        info = {
            "title": None,
            "description": "Great lib.",
            "features": [],
            "installation": None,
            "usage": None,
            "examples": [],
        }
        result = self.seeker._format_readme_analysis(info)
        assert "Great lib." in result

    def test_includes_features(self) -> None:
        info = {
            "title": None,
            "description": None,
            "features": ["Fast", "Simple"],
            "installation": None,
            "usage": None,
            "examples": [],
        }
        result = self.seeker._format_readme_analysis(info)
        assert "Fast" in result
        assert "Simple" in result

    def test_includes_installation(self) -> None:
        info = {
            "title": None,
            "description": None,
            "features": [],
            "installation": "pip install x",
            "usage": None,
            "examples": [],
        }
        result = self.seeker._format_readme_analysis(info)
        assert "pip install x" in result

    def test_includes_usage(self) -> None:
        info = {
            "title": None,
            "description": None,
            "features": [],
            "installation": None,
            "usage": "import x; x.run()",
            "examples": [],
        }
        result = self.seeker._format_readme_analysis(info)
        assert "import x" in result

    def test_includes_examples_header_when_examples_present(self) -> None:
        info = {
            "title": None,
            "description": None,
            "features": [],
            "installation": None,
            "usage": None,
            "examples": ["print('hello')"],
        }
        result = self.seeker._format_readme_analysis(info)
        assert "Code Examples" in result

    def test_shows_only_first_example_preview(self) -> None:
        info = {
            "title": None,
            "description": None,
            "features": [],
            "installation": None,
            "usage": None,
            "examples": ["first = 1", "second = 2"],
        }
        result = self.seeker._format_readme_analysis(info)
        assert "first = 1" in result
        assert "second = 2" not in result

    def test_empty_info_returns_empty_string(self) -> None:
        info = {"title": None, "description": None, "features": [], "installation": None, "usage": None, "examples": []}
        result = self.seeker._format_readme_analysis(info)
        assert result == ""

    def test_returns_string(self) -> None:
        info = {"title": "T", "description": None, "features": [], "installation": None, "usage": None, "examples": []}
        result = self.seeker._format_readme_analysis(info)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._clone_repository
# ---------------------------------------------------------------------------


class TestCloneRepository:
    """Tests for _clone_repository."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.seeker._clone_repository("https://github.com/o/r", tmp_path)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_nonzero_returncode(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 128
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fatal: not found"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await self.seeker._clone_repository("https://github.com/o/bad", tmp_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, tmp_path: Path) -> None:
        with patch("asyncio.create_subprocess_exec", side_effect=OSError("no git")):
            result = await self.seeker._clone_repository("https://github.com/o/r", tmp_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_uses_shallow_clone_flags(self, tmp_path: Path) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await self.seeker._clone_repository("https://github.com/o/r", tmp_path)
            call_args = mock_exec.call_args[0]
            assert "--depth" in call_args
            assert "1" in call_args


# ---------------------------------------------------------------------------
# GitHubSkillSeeker.execute — routing
# ---------------------------------------------------------------------------


class TestExecuteRouting:
    """Tests for GitHubSkillSeeker.execute routing."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_failure(self) -> None:
        # ToolResult uses `message` field; source passes `result=` (extra field,
        # silently dropped by Pydantic). Only `success` is reliable here.
        result = await self.seeker.execute("nonexistent_tool", {})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_routes_github_discover_skill(self) -> None:
        self.seeker._discover_skill = AsyncMock(return_value=MagicMock(success=True, result="ok"))
        result = await self.seeker.execute(
            "github_discover_skill",
            {"repo_url": "owner/repo", "skill_name": "my_skill"},
        )
        self.seeker._discover_skill.assert_awaited_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_routes_github_analyze_readme(self) -> None:
        self.seeker._analyze_readme = AsyncMock(return_value=MagicMock(success=True, result="readme"))
        await self.seeker.execute(
            "github_analyze_readme",
            {"repo_url": "owner/repo"},
        )
        self.seeker._analyze_readme.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_discover_skill_uses_default_include_examples(self) -> None:
        self.seeker._discover_skill = AsyncMock(return_value=MagicMock(success=True))
        await self.seeker.execute("github_discover_skill", {"repo_url": "owner/repo"})
        _, kwargs = self.seeker._discover_skill.call_args
        assert kwargs.get("include_examples", True) is True

    @pytest.mark.asyncio
    async def test_discover_skill_passes_focus_paths(self) -> None:
        self.seeker._discover_skill = AsyncMock(return_value=MagicMock(success=True))
        await self.seeker.execute(
            "github_discover_skill",
            {"repo_url": "owner/repo", "focus_paths": ["src/"]},
        )
        _, kwargs = self.seeker._discover_skill.call_args
        assert kwargs.get("focus_paths") == ["src/"]


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._discover_skill integration
# ---------------------------------------------------------------------------


class TestDiscoverSkill:
    """Integration tests for _discover_skill."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    @pytest.mark.asyncio
    async def test_returns_failure_when_clone_fails(self) -> None:
        self.seeker._clone_repository = AsyncMock(return_value=False)
        result = await self.seeker._discover_skill(
            repo_url="https://github.com/o/r",
            skill_name=None,
            focus_paths=[],
            include_examples=True,
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_returns_failure_on_exception(self) -> None:
        self.seeker._clone_repository = AsyncMock(side_effect=RuntimeError("network error"))
        result = await self.seeker._discover_skill(
            repo_url="https://github.com/o/r",
            skill_name=None,
            focus_paths=[],
            include_examples=True,
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_uses_repo_name_when_skill_name_not_provided(self, tmp_path: Path) -> None:
        analysis = _make_analysis(name="my-cool-repo")
        pkg = _make_skill_package_mock(name="my_cool_repo")

        self.seeker._clone_repository = AsyncMock(return_value=True)
        self.seeker._analyze_repository = AsyncMock(return_value=analysis)
        self.seeker._generate_skill_package = MagicMock(return_value=pkg)
        self.seeker._format_discovery_result = MagicMock(return_value="formatted")

        result = await self.seeker._discover_skill(
            repo_url="https://github.com/o/my-cool-repo",
            skill_name=None,
            focus_paths=[],
            include_examples=True,
        )

        assert result.success is True
        call_kwargs = self.seeker._generate_skill_package.call_args[1]
        assert call_kwargs["skill_name"] == "my_cool_repo"

    @pytest.mark.asyncio
    async def test_uses_provided_skill_name(self) -> None:
        analysis = _make_analysis(name="repo")
        pkg = _make_skill_package_mock()

        self.seeker._clone_repository = AsyncMock(return_value=True)
        self.seeker._analyze_repository = AsyncMock(return_value=analysis)
        self.seeker._generate_skill_package = MagicMock(return_value=pkg)
        self.seeker._format_discovery_result = MagicMock(return_value="done")

        await self.seeker._discover_skill(
            repo_url="https://github.com/o/repo",
            skill_name="custom_name",
            focus_paths=[],
            include_examples=True,
        )

        call_kwargs = self.seeker._generate_skill_package.call_args[1]
        assert call_kwargs["skill_name"] == "custom_name"

    @pytest.mark.asyncio
    async def test_result_data_contains_analysis_info(self) -> None:
        funcs = [_make_extracted_function(name=f"fn{i}") for i in range(3)]
        classes = [_make_extracted_class(name=f"Cls{i}") for i in range(2)]
        analysis = _make_analysis(
            name="testrepo",
            description="Test repo",
            functions=funcs,
            classes=classes,
            dependencies=["httpx"],
        )
        pkg = _make_skill_package_mock()

        self.seeker._clone_repository = AsyncMock(return_value=True)
        self.seeker._analyze_repository = AsyncMock(return_value=analysis)
        self.seeker._generate_skill_package = MagicMock(return_value=pkg)
        self.seeker._format_discovery_result = MagicMock(return_value="done")

        result = await self.seeker._discover_skill(
            repo_url="https://github.com/o/testrepo",
            skill_name="testrepo",
            focus_paths=[],
            include_examples=True,
        )

        assert result.success is True
        assert result.data["analysis"]["functions_count"] == 3
        assert result.data["analysis"]["classes_count"] == 2
        assert "httpx" in result.data["analysis"]["dependencies"]


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._analyze_readme integration
# ---------------------------------------------------------------------------


class TestAnalyzeReadme:
    """Integration tests for _analyze_readme."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    @pytest.mark.asyncio
    async def test_returns_failure_when_clone_fails(self) -> None:
        self.seeker._clone_repository = AsyncMock(return_value=False)
        result = await self.seeker._analyze_readme("https://github.com/o/r")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_returns_failure_when_no_readme(self) -> None:
        self.seeker._clone_repository = AsyncMock(return_value=True)
        self.seeker._find_and_read_readme = MagicMock(return_value=None)
        result = await self.seeker._analyze_readme("https://github.com/o/r")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_returns_success_with_readme_info(self) -> None:
        readme = "# My Project\n\nDoes things.\n\n## Features\n\n- Fast\n"
        self.seeker._clone_repository = AsyncMock(return_value=True)
        self.seeker._find_and_read_readme = MagicMock(return_value=readme)

        result = await self.seeker._analyze_readme("https://github.com/o/r")

        assert result.success is True
        assert isinstance(result.data, dict)
        assert result.data["title"] == "My Project"

    @pytest.mark.asyncio
    async def test_returns_failure_on_exception(self) -> None:
        self.seeker._clone_repository = AsyncMock(side_effect=ValueError("oops"))
        result = await self.seeker._analyze_readme("https://github.com/o/r")
        assert result.success is False


# ---------------------------------------------------------------------------
# GitHubSkillSeeker._generate_skill_package
# ---------------------------------------------------------------------------


class TestGenerateSkillPackage:
    """Tests for _generate_skill_package."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_calls_packager_create_package(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        analysis = _make_analysis()
        result = self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="test_skill",
            repo_url="https://github.com/o/r",
            include_examples=True,
        )
        self.seeker._packager.create_package.assert_called_once()
        assert result is pkg

    def test_workflow_has_three_steps(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        analysis = _make_analysis()
        self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="skill",
            repo_url="https://github.com/o/r",
            include_examples=True,
        )
        call_kwargs = self.seeker._packager.create_package.call_args[1]
        assert len(call_kwargs["metadata"].workflow_steps) == 3

    def test_skips_examples_when_include_examples_false(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        analysis = _make_analysis(examples_found=["examples/demo.py"])
        self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="skill",
            repo_url="https://github.com/o/r",
            include_examples=False,
        )
        call_kwargs = self.seeker._packager.create_package.call_args[1]
        assert call_kwargs["metadata"].examples == []

    def test_includes_examples_when_include_examples_true(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        analysis = _make_analysis(examples_found=["examples/demo.py", "examples/advanced.py"])
        self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="skill",
            repo_url="https://github.com/o/r",
            include_examples=True,
        )
        call_kwargs = self.seeker._packager.create_package.call_args[1]
        assert len(call_kwargs["metadata"].examples) > 0

    def test_metadata_name_matches_skill_name(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        analysis = _make_analysis()
        self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="awesome_skill",
            repo_url="https://github.com/o/r",
            include_examples=True,
        )
        call_kwargs = self.seeker._packager.create_package.call_args[1]
        assert call_kwargs["metadata"].name == "awesome_skill"

    def test_dependencies_included_in_metadata(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        analysis = _make_analysis(dependencies=["httpx", "pydantic"])
        self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="skill",
            repo_url="https://github.com/o/r",
            include_examples=True,
        )
        call_kwargs = self.seeker._packager.create_package.call_args[1]
        assert "httpx" in call_kwargs["metadata"].python_dependencies

    def test_feature_categories_built_from_classes(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        method = _make_extracted_function(name="compute", docstring="Compute the result.")
        cls = _make_extracted_class(name="Engine", methods=[method])
        analysis = _make_analysis(classes=[cls])
        self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="skill",
            repo_url="https://github.com/o/r",
            include_examples=True,
        )
        call_kwargs = self.seeker._packager.create_package.call_args[1]
        assert len(call_kwargs["metadata"].feature_categories) > 0

    def test_scripts_included_in_call(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        analysis = _make_analysis()
        self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="skill",
            repo_url="https://github.com/o/r",
            include_examples=True,
        )
        call_kwargs = self.seeker._packager.create_package.call_args[1]
        assert len(call_kwargs["scripts"]) >= 1

    def test_references_included_in_call(self) -> None:
        pkg = _make_skill_package_mock()
        self.seeker._packager.create_package = MagicMock(return_value=pkg)
        analysis = _make_analysis()
        self.seeker._generate_skill_package(
            analysis=analysis,
            skill_name="skill",
            repo_url="https://github.com/o/r",
            include_examples=True,
        )
        call_kwargs = self.seeker._packager.create_package.call_args[1]
        assert len(call_kwargs["references"]) >= 1


# ---------------------------------------------------------------------------
# GitHubSkillSeeker — tool schema declarations
# ---------------------------------------------------------------------------


class TestToolSchemas:
    """Tests for GitHubSkillSeeker.tools schema declarations."""

    def setup_method(self) -> None:
        self.seeker = _make_seeker()

    def test_has_two_tool_schemas(self) -> None:
        assert len(GitHubSkillSeeker.tools) == 2

    def test_github_discover_skill_schema_exists(self) -> None:
        names = [t.name for t in GitHubSkillSeeker.tools]
        assert "github_discover_skill" in names

    def test_github_analyze_readme_schema_exists(self) -> None:
        names = [t.name for t in GitHubSkillSeeker.tools]
        assert "github_analyze_readme" in names

    def test_github_discover_skill_requires_repo_url(self) -> None:
        schema = next(t for t in GitHubSkillSeeker.tools if t.name == "github_discover_skill")
        assert "repo_url" in schema.required

    def test_github_analyze_readme_requires_repo_url(self) -> None:
        schema = next(t for t in GitHubSkillSeeker.tools if t.name == "github_analyze_readme")
        assert "repo_url" in schema.required

    def test_github_discover_skill_has_optional_fields(self) -> None:
        schema = next(t for t in GitHubSkillSeeker.tools if t.name == "github_discover_skill")
        assert "skill_name" in schema.parameters
        assert "focus_paths" in schema.parameters
        assert "include_examples" in schema.parameters

    def test_tool_names_are_strings(self) -> None:
        for tool in GitHubSkillSeeker.tools:
            assert isinstance(tool.name, str)

    def test_tool_descriptions_are_non_empty(self) -> None:
        for tool in GitHubSkillSeeker.tools:
            assert isinstance(tool.description, str)
            assert len(tool.description) > 0
