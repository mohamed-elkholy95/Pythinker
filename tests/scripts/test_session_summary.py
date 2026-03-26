from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_session_summary_module() -> object:
    module_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "ai" / "session_summary.py"
    )
    spec = importlib.util.spec_from_file_location("session_summary", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load session_summary module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def test_build_session_summary_uses_latest_session_and_summary(tmp_path: Path) -> None:
    module = load_session_summary_module()
    write_json(
        tmp_path / ".codex" / "session" / "latest-session.json",
        {
            "branch": "feature-x",
            "head": "abc123",
            "modified_files": ["skills/a", "scripts/b"],
        },
    )
    write_json(
        tmp_path / ".codex" / "session" / "latest-summary.json",
        {"status": [" M skills/a", "?? scripts/b"], "ended_at": "2026-03-22T00:00:00Z"},
    )

    summary = module.build_session_summary(tmp_path)

    assert summary["branch"] == "feature-x"
    assert summary["head"] == "abc123"
    assert summary["changed_entries"] == 2
    assert summary["tracked_paths"] == ["skills/a", "scripts/b"]


def test_build_session_summary_handles_missing_files(tmp_path: Path) -> None:
    module = load_session_summary_module()

    summary = module.build_session_summary(tmp_path)

    assert summary["branch"] == "unknown"
    assert summary["changed_entries"] == 0
    assert summary["tracked_paths"] == []


def test_build_session_summary_normalizes_git_status_lines(tmp_path: Path) -> None:
    module = load_session_summary_module()
    write_json(
        tmp_path / ".codex" / "session" / "latest-session.json",
        {
            "branch": "feature-y",
            "head": "def456",
            "modified_files": [" M skills/a", "?? scripts/b"],
        },
    )
    write_json(
        tmp_path / ".codex" / "session" / "latest-summary.json",
        {"status": [" M skills/a", "?? scripts/b"], "ended_at": "2026-03-22T00:00:00Z"},
    )

    summary = module.build_session_summary(tmp_path)

    assert summary["tracked_paths"] == ["skills/a", "scripts/b"]
