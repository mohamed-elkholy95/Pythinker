from __future__ import annotations

import json
import re
from pathlib import Path


def _read_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def build_session_summary(repo_root: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    session_dir = repo_root / ".codex" / "session"
    latest_session = _read_json(session_dir / "latest-session.json")
    latest_summary = _read_json(session_dir / "latest-summary.json")

    tracked_paths = []
    for path in latest_session.get("modified_files", []):
        if isinstance(path, str):
            tracked_paths.append(re.sub(r"^\s*[A-Z?]{1,2}\s+", "", path))

    status_entries = latest_summary.get("status", [])
    changed_entries = len(status_entries) if isinstance(status_entries, list) else 0

    return {
        "repo_root": str(repo_root),
        "branch": latest_session.get("branch", "unknown") or "unknown",
        "head": latest_session.get("head", "unknown") or "unknown",
        "changed_entries": changed_entries,
        "tracked_paths": tracked_paths,
        "ended_at": latest_summary.get("ended_at"),
    }


def main() -> None:
    print(json.dumps(build_session_summary(Path.cwd()), indent=2))


if __name__ == "__main__":
    main()
