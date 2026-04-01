from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_codex_doctor_module() -> object:
    module_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "ai" / "codex_doctor.py"
    )
    spec = importlib.util.spec_from_file_location("codex_doctor", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load codex_doctor module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def test_codex_doctor_reports_aggregated_status(tmp_path: Path) -> None:
    module = load_codex_doctor_module()

    write_file(tmp_path / "AGENTS.md", "# AGENTS\n- `AGENTS.md` is repo law.\n")
    write_file(tmp_path / "instructions.md", "# Instructions\n")
    write_file(tmp_path / ".codex" / "README.md", "# Codex\n")
    write_file(tmp_path / ".opencode" / "agents" / "build.md", "- `.codex/` is the primary repo-local harness layer.\n")
    write_file(tmp_path / ".opencode" / "agents" / "plan.md", "- `.codex/` is the primary repo-local harness layer.\n")
    write_file(tmp_path / ".cursor" / "rules" / "core.mdc", "- `.codex/` is the primary repo-local harness layer.\n")
    write_file(
        tmp_path / "skills" / "alpha" / "SKILL.md",
        "---\nname: alpha\ndescription: Alpha skill\n---\n\n# Alpha\n",
    )
    write_file(
        tmp_path / "skills" / "beta" / "SKILL.md",
        "---\nname: beta\n---\n\n# Beta\n",
    )
    write_json(
        tmp_path / ".codex" / "session" / "latest-session.json",
        {
            "branch": "feature/codex-doctor",
            "head": "abc123",
            "modified_files": [" M skills/alpha/SKILL.md"],
        },
    )
    write_json(
        tmp_path / ".codex" / "session" / "latest-summary.json",
        {"status": [" M skills/alpha/SKILL.md"], "ended_at": "2026-03-22T00:00:00Z"},
    )

    report = module.build_codex_doctor_report(tmp_path)

    assert report["status"] == "attention"
    assert report["harness"]["missing_files"] == []
    assert report["session"]["branch"] == "feature/codex-doctor"
    assert report["issues"]
    assert any("description" in issue.lower() for issue in report["issues"])
    assert any(
        "cd frontend && bun run lint:check && bun run type-check"
        in command
        for command in report["recommended_commands"]
    )


def test_codex_doctor_reports_ok_when_inputs_are_clean(tmp_path: Path) -> None:
    module = load_codex_doctor_module()

    write_file(tmp_path / "AGENTS.md", "# AGENTS\n- `AGENTS.md` is repo law.\n- `.codex/` is the primary repo-local harness layer.\n")
    write_file(tmp_path / "instructions.md", "# Instructions\n")
    write_file(tmp_path / ".codex" / "README.md", "# Codex\n")
    write_file(
        tmp_path / ".opencode" / "agents" / "build.md",
        "- Build adapter stays in sync with `.codex` and repo law.\n",
    )
    write_file(
        tmp_path / ".opencode" / "agents" / "plan.md",
        "- Plan adapter stays in sync with `.codex` and repo law.\n",
    )
    write_file(
        tmp_path / ".cursor" / "rules" / "core.mdc",
        "- Cursor core rules mirror the `.codex` contract.\n",
    )
    write_file(
        tmp_path / "skills" / "alpha" / "SKILL.md",
        "---\nname: alpha\ndescription: Alpha skill\n---\n\n# Alpha\n",
    )

    report = module.build_codex_doctor_report(tmp_path)

    assert report["status"] == "ok"
    assert report["issues"] == []
