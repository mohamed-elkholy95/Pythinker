"""Tests that DDD layer boundaries are respected.

Checks:
  - Domain must not import infrastructure or application
  - Application must not import interfaces
  - Interface routes must not import infrastructure directly (use application services)
"""

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
    "agent_task_runner.py",  # Orchestrator that bridges domain/application for screenshot capture
    "memory_service.py",  # Uses infra outbox repository for Phase 2 Mongo->Qdrant sync
    "sync_worker.py",  # Domain sync orchestration still constructs infra repositories directly
    "reconciliation_job.py",  # Reconciliation job currently depends on infra db/repo implementations
    "conversation_context_service.py",  # Uses embedding client + qdrant repo for vectorized context
    "knowledge_base_service.py",  # Uses infra adapter + repository types under TYPE_CHECKING
    "message_router.py",  # Uses AgentService under TYPE_CHECKING for channel-to-agent bridge
    "llm_grounding_verifier.py",  # Singleton factory constructs UniversalLLM (infra) for LLM-as-Judge
}


def _get_domain_python_files():
    """Get all Python files in domain layer."""
    domain_dir = os.path.join(os.path.dirname(__file__), "..", "app", "domain")
    domain_dir = os.path.abspath(domain_dir)
    files = []
    for root, _, filenames in os.walk(domain_dir):
        files.extend(os.path.join(root, f) for f in filenames if f.endswith(".py") and not f.startswith("__"))
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
            violations.extend(
                f"{filepath}:{node.lineno} imports {node.module}"
                for prefix in forbidden
                if node.module.startswith(prefix)
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                violations.extend(
                    f"{filepath}:{node.lineno} imports {alias.name}"
                    for prefix in forbidden
                    if alias.name.startswith(prefix)
                )
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

    # Filter out known runtime-only imports in plan_act.py (pre-existing)
    all_violations = [v for v in all_violations if "docker_sandbox" not in v and "canvas_service" not in v]

    if all_violations:
        msg = "Domain layer violations found:\n" + "\n".join(all_violations)
        pytest.fail(msg)


def _get_application_python_files():
    """Get all Python files in application layer."""
    app_dir = os.path.join(os.path.dirname(__file__), "..", "app", "application")
    app_dir = os.path.abspath(app_dir)
    files = []
    for root, _, filenames in os.walk(app_dir):
        files.extend(os.path.join(root, f) for f in filenames if f.endswith(".py") and not f.startswith("__"))
    return files


def test_application_layer_does_not_import_interfaces():
    """Application layer must not import from interfaces layer."""
    violations = []
    for filepath in _get_application_python_files():
        violations.extend(_check_imports(filepath, ["app.interfaces."]))

    if violations:
        pytest.fail("Application->Interfaces violations:\n" + "\n".join(violations))


def _get_interfaces_python_files():
    """Get all Python files in interfaces layer."""
    iface_dir = os.path.join(os.path.dirname(__file__), "..", "app", "interfaces")
    iface_dir = os.path.abspath(iface_dir)
    files = []
    for root, _, filenames in os.walk(iface_dir):
        files.extend(os.path.join(root, f) for f in filenames if f.endswith(".py") and not f.startswith("__"))
    return files


# Pre-existing interfaces->infrastructure violations tracked for future cleanup.
# dependencies.py is the composition root (wires concrete impls to abstractions).
# Routes below import infrastructure directly instead of going through application services.
KNOWN_IFACE_EXCEPTIONS = {
    "dependencies.py",
    "exception_handlers.py",
    "skills_routes.py",
    "metrics_routes.py",
    "knowledge_base_routes.py",  # Uses infra repository type under TYPE_CHECKING
    "gateway_runner.py",  # Composition root for channel gateway service
    "channel_link_routes.py",  # Wires infra repos for account linking endpoints
}


def test_interfaces_do_not_bypass_application_layer():
    """Interface routes should use application services, not import infrastructure directly.

    Known exceptions are tracked in KNOWN_IFACE_EXCEPTIONS for future cleanup.
    New routes must go through the application layer.
    """
    violations = []
    for filepath in _get_interfaces_python_files():
        filename = os.path.basename(filepath)
        if filename in KNOWN_IFACE_EXCEPTIONS:
            continue
        violations.extend(_check_imports(filepath, ["app.infrastructure."]))

    if violations:
        pytest.fail("Interfaces->Infrastructure violations:\n" + "\n".join(violations))
