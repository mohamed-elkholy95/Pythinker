"""Tests for CodeExecutorTool data models, enums, and constants.

Covers:
- Language enum members and string behaviour
- MAX_TIMEOUT_SECONDS constant
- LANGUAGE_CONFIG mapping integrity and required keys
- ExecutionResult dataclass construction and to_dict serialisation
- Artifact dataclass construction and to_dict serialisation
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.services.tools.code_executor import (
    LANGUAGE_CONFIG,
    MAX_TIMEOUT_SECONDS,
    Artifact,
    ExecutionResult,
    Language,
)


# ---------------------------------------------------------------------------
# Language enum
# ---------------------------------------------------------------------------
class TestLanguageEnum:
    """Language is a str-Enum — values must be lowercase, usable as dict keys."""

    def test_all_members_present(self) -> None:
        names = {m.name for m in Language}
        assert names == {"PYTHON", "JAVASCRIPT", "BASH", "SQL"}

    def test_python_value(self) -> None:
        assert Language.PYTHON == "python"
        assert Language.PYTHON.value == "python"

    def test_javascript_value(self) -> None:
        assert Language.JAVASCRIPT == "javascript"
        assert Language.JAVASCRIPT.value == "javascript"

    def test_bash_value(self) -> None:
        assert Language.BASH == "bash"
        assert Language.BASH.value == "bash"

    def test_sql_value(self) -> None:
        assert Language.SQL == "sql"
        assert Language.SQL.value == "sql"

    def test_is_str_subclass(self) -> None:
        assert isinstance(Language.PYTHON, str)
        assert isinstance(Language.BASH, str)

    def test_lookup_from_string(self) -> None:
        assert Language("python") is Language.PYTHON
        assert Language("javascript") is Language.JAVASCRIPT
        assert Language("bash") is Language.BASH
        assert Language("sql") is Language.SQL

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            Language("ruby")

    def test_case_sensitive_lookup(self) -> None:
        """Enum values are lowercase; uppercase input must raise."""
        with pytest.raises(ValueError):
            Language("Python")

    def test_usable_as_dict_key(self) -> None:
        """Language members must be hashable and usable as mapping keys."""
        mapping = {Language.PYTHON: "py", Language.BASH: "sh"}
        assert mapping[Language.PYTHON] == "py"

    def test_equality_with_plain_string(self) -> None:
        """str-Enum equality check against bare string values."""
        assert Language.PYTHON == "python"
        assert Language.JAVASCRIPT == "javascript"

    def test_str_representation(self) -> None:
        # str(StrEnum member) returns the value directly, but plain str(Enum)
        # returns "EnumClass.MEMBER".  Language is a str subclass so the value
        # IS "python"; equality checks against the bare string work because of
        # __eq__, but str() formatting depends on the Python version.
        # What is guaranteed: the .value attribute is the canonical string.
        assert Language.PYTHON.value == "python"
        assert Language.SQL.value == "sql"


# ---------------------------------------------------------------------------
# MAX_TIMEOUT_SECONDS constant
# ---------------------------------------------------------------------------
class TestMaxTimeoutSeconds:
    def test_value_is_600(self) -> None:
        assert MAX_TIMEOUT_SECONDS == 600

    def test_is_int(self) -> None:
        assert isinstance(MAX_TIMEOUT_SECONDS, int)

    def test_exceeds_any_language_default(self) -> None:
        """MAX_TIMEOUT_SECONDS must cap every language's timeout_default."""
        for lang, cfg in LANGUAGE_CONFIG.items():
            default = cfg["timeout_default"]
            assert default <= MAX_TIMEOUT_SECONDS, (
                f"{lang} timeout_default {default} exceeds MAX_TIMEOUT_SECONDS {MAX_TIMEOUT_SECONDS}"
            )


# ---------------------------------------------------------------------------
# LANGUAGE_CONFIG mapping
# ---------------------------------------------------------------------------
_REQUIRED_KEYS = {
    "interpreter",
    "package_manager",
    "install_cmd",
    "file_extension",
    "run_cmd",
    "timeout_default",
    "shebang",
}


class TestLanguageConfig:
    """LANGUAGE_CONFIG must define all required keys for every Language member."""

    def test_all_languages_have_config_entry(self) -> None:
        for lang in Language:
            assert lang in LANGUAGE_CONFIG, f"{lang!r} missing from LANGUAGE_CONFIG"

    def test_no_extra_keys_in_config(self) -> None:
        """Config must not contain keys for languages outside the Language enum."""
        valid_values = {lang.value for lang in Language}
        for key in LANGUAGE_CONFIG:
            assert str(key) in valid_values or key in Language, f"Unexpected key {key!r} in LANGUAGE_CONFIG"

    @pytest.mark.parametrize("lang", list(Language))
    def test_required_keys_present(self, lang: Language) -> None:
        cfg = LANGUAGE_CONFIG[lang]
        missing = _REQUIRED_KEYS - cfg.keys()
        assert not missing, f"{lang} config missing keys: {missing}"

    @pytest.mark.parametrize("lang", list(Language))
    def test_timeout_default_is_positive_int(self, lang: Language) -> None:
        timeout = LANGUAGE_CONFIG[lang]["timeout_default"]
        assert isinstance(timeout, int)
        assert timeout > 0

    @pytest.mark.parametrize("lang", list(Language))
    def test_file_extension_starts_with_dot(self, lang: Language) -> None:
        ext = LANGUAGE_CONFIG[lang]["file_extension"]
        assert isinstance(ext, str)
        assert ext.startswith("."), f"{lang} file_extension {ext!r} must start with '.'"

    # --- Python-specific ---

    def test_python_interpreter(self) -> None:
        assert LANGUAGE_CONFIG[Language.PYTHON]["interpreter"] == "python3"

    def test_python_package_manager(self) -> None:
        assert LANGUAGE_CONFIG[Language.PYTHON]["package_manager"] == "pip3"

    def test_python_file_extension(self) -> None:
        assert LANGUAGE_CONFIG[Language.PYTHON]["file_extension"] == ".py"

    def test_python_run_cmd(self) -> None:
        assert LANGUAGE_CONFIG[Language.PYTHON]["run_cmd"] == "python3"

    def test_python_shebang(self) -> None:
        shebang = LANGUAGE_CONFIG[Language.PYTHON]["shebang"]
        assert shebang is not None
        assert shebang.startswith("#!")

    def test_python_install_cmd_contains_pip(self) -> None:
        install = LANGUAGE_CONFIG[Language.PYTHON]["install_cmd"]
        assert install is not None
        assert "pip" in install

    # --- JavaScript-specific ---

    def test_javascript_interpreter(self) -> None:
        assert LANGUAGE_CONFIG[Language.JAVASCRIPT]["interpreter"] == "node"

    def test_javascript_package_manager(self) -> None:
        assert LANGUAGE_CONFIG[Language.JAVASCRIPT]["package_manager"] == "npm"

    def test_javascript_file_extension(self) -> None:
        assert LANGUAGE_CONFIG[Language.JAVASCRIPT]["file_extension"] == ".js"

    def test_javascript_run_cmd(self) -> None:
        assert LANGUAGE_CONFIG[Language.JAVASCRIPT]["run_cmd"] == "node"

    def test_javascript_shebang(self) -> None:
        shebang = LANGUAGE_CONFIG[Language.JAVASCRIPT]["shebang"]
        assert shebang is not None
        assert "node" in shebang

    def test_javascript_install_cmd_contains_npm(self) -> None:
        install = LANGUAGE_CONFIG[Language.JAVASCRIPT]["install_cmd"]
        assert install is not None
        assert "npm" in install

    # --- Bash-specific ---

    def test_bash_interpreter(self) -> None:
        assert LANGUAGE_CONFIG[Language.BASH]["interpreter"] == "bash"

    def test_bash_package_manager_is_none(self) -> None:
        assert LANGUAGE_CONFIG[Language.BASH]["package_manager"] is None

    def test_bash_install_cmd_is_none(self) -> None:
        assert LANGUAGE_CONFIG[Language.BASH]["install_cmd"] is None

    def test_bash_file_extension(self) -> None:
        assert LANGUAGE_CONFIG[Language.BASH]["file_extension"] == ".sh"

    def test_bash_shebang(self) -> None:
        shebang = LANGUAGE_CONFIG[Language.BASH]["shebang"]
        assert shebang is not None
        assert "bash" in shebang

    def test_bash_timeout_lower_than_python(self) -> None:
        """Bash has a shorter default timeout than Python/JS."""
        bash_t = LANGUAGE_CONFIG[Language.BASH]["timeout_default"]
        python_t = LANGUAGE_CONFIG[Language.PYTHON]["timeout_default"]
        assert bash_t < python_t

    # --- SQL-specific ---

    def test_sql_interpreter(self) -> None:
        assert LANGUAGE_CONFIG[Language.SQL]["interpreter"] == "sqlite3"

    def test_sql_package_manager_is_none(self) -> None:
        assert LANGUAGE_CONFIG[Language.SQL]["package_manager"] is None

    def test_sql_install_cmd_is_none(self) -> None:
        assert LANGUAGE_CONFIG[Language.SQL]["install_cmd"] is None

    def test_sql_file_extension(self) -> None:
        assert LANGUAGE_CONFIG[Language.SQL]["file_extension"] == ".sql"

    def test_sql_run_cmd(self) -> None:
        assert LANGUAGE_CONFIG[Language.SQL]["run_cmd"] == "sqlite3"

    def test_sql_shebang_is_none(self) -> None:
        assert LANGUAGE_CONFIG[Language.SQL]["shebang"] is None

    def test_sql_timeout_shortest(self) -> None:
        """SQL has the shortest default timeout."""
        sql_t = LANGUAGE_CONFIG[Language.SQL]["timeout_default"]
        for lang in (Language.PYTHON, Language.JAVASCRIPT, Language.BASH):
            assert sql_t <= LANGUAGE_CONFIG[lang]["timeout_default"], f"SQL timeout {sql_t} should be <= {lang} timeout"


# ---------------------------------------------------------------------------
# ExecutionResult dataclass
# ---------------------------------------------------------------------------
class TestExecutionResult:
    """ExecutionResult stores code-execution outcomes and serialises cleanly."""

    def test_minimal_construction_success(self) -> None:
        result = ExecutionResult(success=True, output="hello")
        assert result.success is True
        assert result.output == "hello"
        assert result.error is None
        assert result.return_code == 0
        assert result.execution_time_ms is None
        assert result.artifacts == []
        assert result.packages_installed == []
        assert result.working_directory is None

    def test_minimal_construction_failure(self) -> None:
        result = ExecutionResult(success=False, output="", error="boom", return_code=1)
        assert result.success is False
        assert result.error == "boom"
        assert result.return_code == 1

    def test_full_construction(self) -> None:
        artifact = {"filename": "chart.png", "path": "/workspace/chart.png", "size_bytes": 1024}
        result = ExecutionResult(
            success=True,
            output="Done",
            error=None,
            return_code=0,
            execution_time_ms=250,
            artifacts=[artifact],
            packages_installed=["pandas", "matplotlib"],
            working_directory="/workspace/abc123",
        )
        assert result.execution_time_ms == 250
        assert result.artifacts == [artifact]
        assert result.packages_installed == ["pandas", "matplotlib"]
        assert result.working_directory == "/workspace/abc123"

    def test_to_dict_keys(self) -> None:
        result = ExecutionResult(success=True, output="ok")
        d = result.to_dict()
        expected_keys = {
            "success",
            "output",
            "error",
            "return_code",
            "execution_time_ms",
            "artifacts",
            "packages_installed",
            "working_directory",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_success_true(self) -> None:
        result = ExecutionResult(success=True, output="all good")
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"] == "all good"
        assert d["error"] is None
        assert d["return_code"] == 0
        assert d["artifacts"] == []
        assert d["packages_installed"] == []

    def test_to_dict_failure(self) -> None:
        result = ExecutionResult(
            success=False,
            output="",
            error="NameError: name 'x' is not defined",
            return_code=1,
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["return_code"] == 1
        assert d["error"] == "NameError: name 'x' is not defined"

    def test_to_dict_with_artifacts(self) -> None:
        artifacts = [
            {"filename": "report.pdf", "path": "/ws/report.pdf", "size_bytes": 4096},
            {"filename": "data.csv", "path": "/ws/data.csv", "size_bytes": 512},
        ]
        result = ExecutionResult(success=True, output="", artifacts=artifacts)
        d = result.to_dict()
        assert d["artifacts"] == artifacts
        assert len(d["artifacts"]) == 2

    def test_to_dict_with_packages(self) -> None:
        result = ExecutionResult(
            success=True,
            output="",
            packages_installed=["numpy==1.26.0", "scipy"],
        )
        d = result.to_dict()
        assert d["packages_installed"] == ["numpy==1.26.0", "scipy"]

    def test_to_dict_with_execution_time(self) -> None:
        result = ExecutionResult(success=True, output="", execution_time_ms=1337)
        d = result.to_dict()
        assert d["execution_time_ms"] == 1337

    def test_to_dict_with_working_directory(self) -> None:
        result = ExecutionResult(
            success=True,
            output="",
            working_directory="/workspace/session-42",
        )
        d = result.to_dict()
        assert d["working_directory"] == "/workspace/session-42"

    def test_artifacts_default_is_independent_per_instance(self) -> None:
        """Mutable default (field(default_factory=list)) must not be shared."""
        r1 = ExecutionResult(success=True, output="")
        r2 = ExecutionResult(success=True, output="")
        r1.artifacts.append({"filename": "a.txt"})
        assert r2.artifacts == [], "Artifact lists must not be shared between instances"

    def test_packages_installed_default_is_independent_per_instance(self) -> None:
        r1 = ExecutionResult(success=True, output="")
        r2 = ExecutionResult(success=True, output="")
        r1.packages_installed.append("requests")
        assert r2.packages_installed == [], "packages_installed must not be shared between instances"

    def test_return_code_non_zero(self) -> None:
        result = ExecutionResult(success=False, output="", return_code=127)
        assert result.return_code == 127
        assert result.to_dict()["return_code"] == 127

    def test_to_dict_returns_new_dict_each_call(self) -> None:
        result = ExecutionResult(success=True, output="hi")
        d1 = result.to_dict()
        d2 = result.to_dict()
        assert d1 == d2
        assert d1 is not d2


# ---------------------------------------------------------------------------
# Artifact dataclass
# ---------------------------------------------------------------------------
class TestArtifact:
    """Artifact stores produced file metadata and serialises cleanly."""

    def test_minimal_construction(self) -> None:
        artifact = Artifact(filename="plot.png", path="/ws/plot.png", size_bytes=2048)
        assert artifact.filename == "plot.png"
        assert artifact.path == "/ws/plot.png"
        assert artifact.size_bytes == 2048
        assert artifact.content_preview is None

    def test_created_at_defaults_to_utc_now(self) -> None:
        before = datetime.now(UTC)
        artifact = Artifact(filename="f.txt", path="/ws/f.txt", size_bytes=0)
        after = datetime.now(UTC)
        assert before <= artifact.created_at <= after
        assert artifact.created_at.tzinfo is not None

    def test_created_at_independent_per_instance(self) -> None:
        a1 = Artifact(filename="a.txt", path="/ws/a.txt", size_bytes=1)
        a2 = Artifact(filename="b.txt", path="/ws/b.txt", size_bytes=1)
        assert a1.created_at is not a2.created_at

    def test_explicit_created_at(self) -> None:
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        artifact = Artifact(filename="f.txt", path="/p", size_bytes=0, created_at=ts)
        assert artifact.created_at == ts

    def test_content_preview_set(self) -> None:
        artifact = Artifact(
            filename="data.csv",
            path="/ws/data.csv",
            size_bytes=500,
            content_preview="id,name\n1,Alice\n",
        )
        assert artifact.content_preview == "id,name\n1,Alice\n"

    def test_to_dict_keys(self) -> None:
        artifact = Artifact(filename="x.txt", path="/ws/x.txt", size_bytes=10)
        d = artifact.to_dict()
        assert set(d.keys()) == {"filename", "path", "size_bytes", "created_at", "content_preview"}

    def test_to_dict_filename_and_path(self) -> None:
        artifact = Artifact(filename="report.md", path="/workspace/session/report.md", size_bytes=1024)
        d = artifact.to_dict()
        assert d["filename"] == "report.md"
        assert d["path"] == "/workspace/session/report.md"

    def test_to_dict_size_bytes(self) -> None:
        artifact = Artifact(filename="f.bin", path="/ws/f.bin", size_bytes=8192)
        d = artifact.to_dict()
        assert d["size_bytes"] == 8192

    def test_to_dict_content_preview_none(self) -> None:
        artifact = Artifact(filename="f.txt", path="/ws/f.txt", size_bytes=0)
        d = artifact.to_dict()
        assert d["content_preview"] is None

    def test_to_dict_content_preview_value(self) -> None:
        artifact = Artifact(
            filename="log.txt",
            path="/ws/log.txt",
            size_bytes=200,
            content_preview="line 1\nline 2\n",
        )
        d = artifact.to_dict()
        assert d["content_preview"] == "line 1\nline 2\n"

    def test_to_dict_created_at_is_iso_string(self) -> None:
        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        artifact = Artifact(filename="f.txt", path="/p", size_bytes=0, created_at=ts)
        d = artifact.to_dict()
        # Must be a valid ISO-8601 string
        assert isinstance(d["created_at"], str)
        parsed = datetime.fromisoformat(d["created_at"])
        assert parsed == ts

    def test_to_dict_created_at_roundtrips(self) -> None:
        artifact = Artifact(filename="x.py", path="/ws/x.py", size_bytes=42)
        d = artifact.to_dict()
        roundtripped = datetime.fromisoformat(d["created_at"])
        assert roundtripped == artifact.created_at

    def test_size_bytes_zero(self) -> None:
        artifact = Artifact(filename="empty.txt", path="/ws/empty.txt", size_bytes=0)
        assert artifact.size_bytes == 0
        assert artifact.to_dict()["size_bytes"] == 0

    def test_to_dict_returns_new_dict_each_call(self) -> None:
        artifact = Artifact(filename="f.txt", path="/p", size_bytes=1)
        d1 = artifact.to_dict()
        d2 = artifact.to_dict()
        assert d1 == d2
        assert d1 is not d2
