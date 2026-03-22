from __future__ import annotations

import importlib.util
from pathlib import Path


def load_harness_audit_module() -> object:
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "ai" / "harness_audit.py"
    spec = importlib.util.spec_from_file_location("harness_audit", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load harness_audit module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_harness_audit_reports_missing_ownership_signals(tmp_path: Path) -> None:
    module = load_harness_audit_module()
    write_file(tmp_path / "AGENTS.md", "# AGENTS\n")
    write_file(tmp_path / "instructions.md", "# Instructions\n")
    write_file(tmp_path / ".codex" / "README.md", "# Codex\n")
    write_file(tmp_path / ".opencode" / "agents" / "build.md", "No codex reference here\n")
    write_file(tmp_path / ".cursor" / "rules" / "core.mdc", "No repo law language here\n")

    report = module.audit_harness(tmp_path)

    assert report["missing_signals"]
    assert any("repo law" in issue.lower() for issue in report["missing_signals"])


def test_harness_audit_reports_duplicate_lines(tmp_path: Path) -> None:
    module = load_harness_audit_module()
    duplicate_line = "- `AGENTS.md` is repo law."
    write_file(tmp_path / "AGENTS.md", f"# AGENTS\n{duplicate_line}\n")
    write_file(tmp_path / "instructions.md", "# Instructions\n")
    write_file(tmp_path / ".codex" / "README.md", "# Codex\n")
    write_file(tmp_path / ".opencode" / "agents" / "build.md", f"{duplicate_line}\n")
    write_file(tmp_path / ".cursor" / "rules" / "core.mdc", f"{duplicate_line}\n")

    report = module.audit_harness(tmp_path)

    assert report["duplicate_lines"]
    assert any(entry["line"] == duplicate_line for entry in report["duplicate_lines"])


def test_harness_audit_reports_missing_codex_adapter_reference(tmp_path: Path) -> None:
    module = load_harness_audit_module()
    write_file(tmp_path / "AGENTS.md", "# AGENTS\n- `AGENTS.md` is repo law.\n")
    write_file(tmp_path / "instructions.md", "# Instructions\n")
    write_file(tmp_path / ".codex" / "README.md", "# Codex\n")
    write_file(tmp_path / ".opencode" / "agents" / "build.md", "Adapter without .codex mention\n")
    write_file(tmp_path / ".cursor" / "rules" / "core.mdc", "- `.codex/` is the primary repo-local harness layer.\n")

    report = module.audit_harness(tmp_path)

    assert any(".codex" in issue for issue in report["missing_signals"])


def test_harness_audit_ignores_metadata_duplicates(tmp_path: Path) -> None:
    module = load_harness_audit_module()
    write_file(tmp_path / "AGENTS.md", "# AGENTS\n")
    write_file(tmp_path / "instructions.md", "# Instructions\n")
    write_file(tmp_path / ".codex" / "README.md", "# Codex\n")
    write_file(tmp_path / ".opencode" / "agents" / "build.md", "alwaysApply: false\n")
    write_file(tmp_path / ".opencode" / "agents" / "plan.md", "alwaysApply: false\n")
    write_file(tmp_path / ".cursor" / "rules" / "core.mdc", "alwaysApply: false\n")
    write_file(tmp_path / ".cursor" / "rules" / "python-backend.mdc", "alwaysApply: false\n")
    write_file(tmp_path / ".cursor" / "rules" / "vue-frontend.mdc", "alwaysApply: false\n")

    report = module.audit_harness(tmp_path)

    assert not any(entry["line"] == "alwaysApply: false" for entry in report["duplicate_lines"])
