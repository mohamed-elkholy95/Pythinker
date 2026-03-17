"""Guardrail: field_validator must be a classmethod (Pydantic v2)."""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _is_field_validator(decorator: ast.AST) -> bool:
    func = decorator.func if isinstance(decorator, ast.Call) else decorator

    if isinstance(func, ast.Name):
        return func.id == "field_validator"
    if isinstance(func, ast.Attribute):
        return func.attr == "field_validator"
    return False


def _is_classmethod(decorator: ast.AST) -> bool:
    if isinstance(decorator, ast.Name):
        return decorator.id == "classmethod"
    if isinstance(decorator, ast.Attribute):
        return decorator.attr == "classmethod"
    return False


def test_field_validators_are_classmethods() -> None:
    offenders: list[str] = []

    for path in APP_ROOT.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            if not node.decorator_list:
                continue

            if any(_is_field_validator(dec) for dec in node.decorator_list) and not any(
                _is_classmethod(dec) for dec in node.decorator_list
            ):
                offenders.append(f"{path}:{node.lineno} {node.name}")

    assert not offenders, "Pydantic v2 field_validator must be a classmethod. Offenders:\n" + "\n".join(offenders)
