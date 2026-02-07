"""Tests that domain layer never imports infrastructure directly."""

import ast
import os

import pytest

# Pre-existing violations tracked for future cleanup.
# These are known violations that exist in skill-related code and
# a sandbox import that require larger refactoring to fix properly.
KNOWN_DOMAIN_EXCEPTIONS = {
    "skill_registry.py",
    "skill_context.py",
    "skill_creator.py",
    "skill_invoke.py",
}


def _get_domain_python_files():
    """Get all Python files in domain layer."""
    domain_dir = os.path.join(os.path.dirname(__file__), "..", "app", "domain")
    domain_dir = os.path.abspath(domain_dir)
    files = []
    for root, _, filenames in os.walk(domain_dir):
        for f in filenames:
            if f.endswith(".py") and not f.startswith("__"):
                files.append(os.path.join(root, f))
    return files


FORBIDDEN_IMPORTS = [
    "app.infrastructure.",
    "app.application.",
]


def _check_imports(filepath: str, forbidden: list[str]) -> list[str]:
    """Check a file for forbidden imports."""
    violations = []
    with open(filepath) as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for prefix in forbidden:
                if node.module.startswith(prefix):
                    violations.append(f"{filepath}:{node.lineno} imports {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden:
                    if alias.name.startswith(prefix):
                        violations.append(f"{filepath}:{node.lineno} imports {alias.name}")
    return violations


def test_domain_layer_has_no_infrastructure_imports():
    """Domain layer must not import from infrastructure or application.

    Known exceptions are tracked in KNOWN_DOMAIN_EXCEPTIONS for future cleanup.
    """
    all_violations = []
    for filepath in _get_domain_python_files():
        filename = os.path.basename(filepath)
        if filename in KNOWN_DOMAIN_EXCEPTIONS:
            continue
        all_violations.extend(_check_imports(filepath, FORBIDDEN_IMPORTS))

    # Filter out the known DockerSandbox import in plan_act.py (pre-existing)
    all_violations = [
        v for v in all_violations
        if "docker_sandbox" not in v
    ]

    if all_violations:
        msg = "Domain layer violations found:\n" + "\n".join(all_violations)
        pytest.fail(msg)


def _get_application_python_files():
    """Get all Python files in application layer."""
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app", "application")
    app_dir = os.path.abspath(app_dir)
    files = []
    for root, _, filenames in os.walk(app_dir):
        for f in filenames:
            if f.endswith(".py") and not f.startswith("__"):
                files.append(os.path.join(root, f))
    return files


# Pre-existing application->interfaces violations tracked for future cleanup.
# agent_service.py imports response schemas from interfaces layer.
KNOWN_APP_EXCEPTIONS = {
    "agent_service.py",
}


def test_application_layer_does_not_import_interfaces():
    """Application layer must not import from interfaces layer."""
    violations = []
    for filepath in _get_application_python_files():
        filename = os.path.basename(filepath)
        if filename in KNOWN_APP_EXCEPTIONS:
            continue
        violations.extend(_check_imports(filepath, ["app.interfaces."]))

    if violations:
        pytest.fail("Application->Interfaces violations:\n" + "\n".join(violations))
