from __future__ import annotations

# ruff: noqa: E402

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ai.harness_audit import audit_harness
from scripts.ai.session_summary import build_session_summary
from scripts.ai.skill_stocktake import stocktake_skills


def _build_issues(report: dict[str, object]) -> list[str]:
    issues: list[str] = []

    harness = report["harness"]
    if isinstance(harness, dict):
        issues.extend(str(item) for item in harness.get("missing_files", []))
        issues.extend(str(item) for item in harness.get("missing_signals", []))
        for duplicate in harness.get("duplicate_lines", []):
            if isinstance(duplicate, dict):
                line = duplicate.get("line", "")
                files = duplicate.get("files", [])
                issues.append(f"duplicate line: {line} ({', '.join(str(file) for file in files)})")

    skills = report["skills"]
    if isinstance(skills, dict):
        issues.extend(str(item) for item in skills.get("warnings", []))

    return issues


def build_codex_doctor_report(repo_root: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    harness_report = audit_harness(repo_root)
    skills_root = repo_root / "skills"
    skills_report = stocktake_skills(skills_root)
    session_report = build_session_summary(repo_root)

    report: dict[str, object] = {
        "repo_root": str(repo_root),
        "harness": harness_report,
        "skills": skills_report,
        "session": session_report,
        "recommended_commands": [
            "cd frontend && bun run lint:check && bun run type-check",
            "cd backend && ruff check . && ruff format --check . && pytest -p no:cov -o addopts= tests/path/to/affected_test.py [tests/more_targeted_files.py ...]",
        ],
    }
    report["issues"] = _build_issues(report)
    report["status"] = "ok" if not report["issues"] else "attention"
    return report


def main() -> None:
    print(json.dumps(build_codex_doctor_report(Path.cwd()), indent=2))


if __name__ == "__main__":
    main()
