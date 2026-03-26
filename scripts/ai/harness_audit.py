from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FILES = [
    "AGENTS.md",
    "instructions.md",
    ".codex/README.md",
    ".opencode/agents/build.md",
    ".opencode/agents/plan.md",
    ".cursor/rules/core.mdc",
]

REQUIRED_SIGNALS = [
    ("AGENTS.md", "repo law", "AGENTS.md should state that it is repo law"),
    ("AGENTS.md", ".codex", "AGENTS.md should mention the Codex-local harness layer"),
    (
        ".opencode/agents/build.md",
        ".codex",
        "OpenCode build adapter should reference .codex",
    ),
    (
        ".opencode/agents/plan.md",
        ".codex",
        "OpenCode plan adapter should reference .codex",
    ),
    (".cursor/rules/core.mdc", ".codex", "Cursor core rules should reference .codex"),
]

DUPLICATE_SCAN_FILES = [
    "AGENTS.md",
    "instructions.md",
    ".codex/README.md",
    ".opencode/agents/build.md",
    ".opencode/agents/plan.md",
    ".cursor/rules/core.mdc",
    ".cursor/rules/python-backend.mdc",
    ".cursor/rules/vue-frontend.mdc",
]

IGNORED_DUPLICATE_LINES = {
    "alwaysApply: false",
    "alwaysApply: true",
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _find_duplicate_lines(repo_root: Path) -> list[dict[str, object]]:
    line_map: dict[str, list[str]] = {}
    for relative_path in DUPLICATE_SCAN_FILES:
        full_path = repo_root / relative_path
        if not full_path.exists():
            continue
        for raw_line in _read_text(full_path).splitlines():
            line = raw_line.strip()
            if (
                len(line) < 18
                or line.startswith("#")
                or line.startswith("---")
                or line in IGNORED_DUPLICATE_LINES
            ):
                continue
            line_map.setdefault(line, []).append(relative_path)

    duplicates: list[dict[str, object]] = []
    for line, files in line_map.items():
        unique_files = sorted(set(files))
        if len(unique_files) > 1:
            duplicates.append({"line": line, "files": unique_files})
    return duplicates


def audit_harness(repo_root: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    missing_files = [path for path in REQUIRED_FILES if not (repo_root / path).exists()]

    missing_signals: list[str] = []
    for relative_path, needle, message in REQUIRED_SIGNALS:
        full_path = repo_root / relative_path
        content = _read_text(full_path)
        if needle not in content:
            missing_signals.append(f"{relative_path}: {message}")

    return {
        "repo_root": str(repo_root),
        "missing_files": missing_files,
        "missing_signals": missing_signals,
        "duplicate_lines": _find_duplicate_lines(repo_root),
    }


def main() -> None:
    report = audit_harness(Path.cwd())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
