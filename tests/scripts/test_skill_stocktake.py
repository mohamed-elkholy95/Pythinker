from __future__ import annotations

import importlib.util
from pathlib import Path


def load_skill_stocktake_module() -> object:
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "ai" / "skill_stocktake.py"
    spec = importlib.util.spec_from_file_location("skill_stocktake", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Failed to load skill_stocktake module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_skill_stocktake_discovers_skills(tmp_path: Path) -> None:
    module = load_skill_stocktake_module()
    write_file(
        tmp_path / "skills" / "alpha" / "SKILL.md",
        "---\nname: alpha\ndescription: Alpha skill\n---\n\n# Alpha\n",
    )
    write_file(
        tmp_path / "skills" / "beta" / "SKILL.md",
        "---\nname: beta\ndescription: Beta skill\n---\n\n# Beta\n",
    )

    report = module.stocktake_skills(tmp_path / "skills")

    assert len(report["skills"]) == 2


def test_skill_stocktake_reports_missing_metadata(tmp_path: Path) -> None:
    module = load_skill_stocktake_module()
    write_file(
        tmp_path / "skills" / "broken" / "SKILL.md",
        "---\nname: broken\n---\n\n# Broken\n",
    )

    report = module.stocktake_skills(tmp_path / "skills")

    assert any("description" in warning.lower() for warning in report["warnings"])


def test_skill_stocktake_reports_likely_overlap(tmp_path: Path) -> None:
    module = load_skill_stocktake_module()
    write_file(
        tmp_path / "skills" / "review-a" / "SKILL.md",
        "---\nname: review-a\ndescription: Review backend changes for regressions and bugs\n---\n\n# Review A\n",
    )
    write_file(
        tmp_path / "skills" / "review-b" / "SKILL.md",
        "---\nname: review-b\ndescription: Review backend changes for regressions and bugs\n---\n\n# Review B\n",
    )

    report = module.stocktake_skills(tmp_path / "skills")

    assert any("overlap" in warning.lower() for warning in report["warnings"])
