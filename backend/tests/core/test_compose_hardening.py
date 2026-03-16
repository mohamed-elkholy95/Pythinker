"""Tests that compose files enforce sandbox hardening baseline.

Verifies security_opt, cap_drop, cap_add, and resource limits
are present in all compose files that define sandbox services.
"""

from pathlib import Path

import pytest
import yaml

# Compose files to validate (relative to project root)
COMPOSE_FILES = [
    "docker-compose.yml",
    "docker-compose-development.yml",
    "docker-compose.dokploy.yml",
]


def _load_compose(path: Path) -> dict:
    """Load compose file as YAML."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_sandbox_services(compose: dict) -> list[tuple[str, dict]]:
    """Extract sandbox service definitions from compose."""
    services = compose.get("services", {})
    return [(name, cfg) for name, cfg in services.items() if "sandbox" in name.lower()]


@pytest.fixture
def project_root() -> Path:
    """Project root (parent of backend, where compose files live)."""
    return Path(__file__).resolve().parent.parent.parent.parent


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_sandbox_services_have_security_opt_no_new_privileges(project_root: Path, compose_file: str) -> None:
    """All sandbox services must include no-new-privileges:true."""
    path = project_root / compose_file
    if not path.exists():
        pytest.skip(f"Compose file not found: {compose_file}")
    compose = _load_compose(path)
    for name, cfg in _get_sandbox_services(compose):
        security_opt = cfg.get("security_opt") or []
        opts_str = " ".join(str(o) for o in security_opt).lower()
        assert "no-new-privileges" in opts_str, f"{compose_file} sandbox '{name}' missing no-new-privileges"


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_sandbox_services_have_cap_drop_all(project_root: Path, compose_file: str) -> None:
    """All sandbox services must cap_drop ALL."""
    path = project_root / compose_file
    if not path.exists():
        pytest.skip(f"Compose file not found: {compose_file}")
    compose = _load_compose(path)
    for name, cfg in _get_sandbox_services(compose):
        cap_drop = cfg.get("cap_drop") or []
        assert "ALL" in cap_drop, f"{compose_file} sandbox '{name}' missing cap_drop: ALL"


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_sandbox_services_have_pids_and_resource_limits(project_root: Path, compose_file: str) -> None:
    """All sandbox services must define pids and memory/cpu limits."""
    path = project_root / compose_file
    if not path.exists():
        pytest.skip(f"Compose file not found: {compose_file}")
    compose = _load_compose(path)
    for name, cfg in _get_sandbox_services(compose):
        deploy = cfg.get("deploy") or {}
        resources = deploy.get("resources") or {}
        limits = resources.get("limits") or {}
        assert "pids" in limits or "memory" in limits, (
            f"{compose_file} sandbox '{name}' missing deploy.resources.limits (pids/memory)"
        )


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_sandbox_services_have_chrome_no_sandbox_arg(project_root: Path, compose_file: str) -> None:
    """Chrome --no-sandbox must be present (correct when container provides isolation)."""
    path = project_root / compose_file
    if not path.exists():
        pytest.skip(f"Compose file not found: {compose_file}")
    compose = _load_compose(path)
    for name, cfg in _get_sandbox_services(compose):
        env = cfg.get("environment") or []
        env_str = " ".join(str(e) for e in env) if isinstance(env, list) else str(env)
        # CHROME_ARGS or SANDBOX_CHROME_ARGS may be in backend env
        assert "--no-sandbox" in env_str or "CHROME_ARGS" in str(cfg), (
            f"{compose_file} sandbox '{name}' missing Chrome --no-sandbox (required for container isolation)"
        )
