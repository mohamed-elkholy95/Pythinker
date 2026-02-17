"""Pytest configuration and fixtures for sandbox API tests."""

import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

# Add the parent directory to Python path so we can import app modules.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.v1.file import router as file_router
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


def create_file_test_app() -> FastAPI:
    """Build a minimal app for file API testing without optional service imports."""
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    app.include_router(file_router, prefix="/api/v1/file", tags=["file"])
    return app


@pytest.fixture(autouse=True)
def _sandbox_base_dir_for_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Override SANDBOX_BASE_DIR so file-API tests can use pytest ``tmp_path``.

    In production the sandbox restricts all paths to ``/home/ubuntu``.
    During local testing ``tmp_path`` lives under ``/tmp`` (or the OS equivalent),
    which would be rejected.  This fixture monkeypatches the module-level constant
    in both ``app.services.file`` and ``app.api.v1.file`` so that the path
    traversal guard accepts ``tmp_path`` as the base directory.
    """
    import app.services.file as file_mod
    import app.api.v1.file as file_api_mod

    resolved_tmp = tmp_path.resolve()
    monkeypatch.setattr(file_mod, "SANDBOX_BASE_DIR", resolved_tmp)
    monkeypatch.setattr(file_api_mod, "SANDBOX_BASE_DIR", resolved_tmp)


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Create an in-process FastAPI test client."""
    with TestClient(create_file_test_app()) as test_client:
        yield test_client


@pytest.fixture
def temp_test_file(client: TestClient, tmp_path: Path) -> Iterator[str]:
    """Create and clean up a temporary file through the file API."""
    temp_file = tmp_path / "test_file.txt"
    content = "Line 1: Hello World\nLine 2: This is a test\nLine 3: Python testing"

    response = client.post(
        "/api/v1/file/write",
        json={"file": str(temp_file), "content": content},
    )
    assert response.status_code == 200

    yield str(temp_file)

    with contextlib.suppress(Exception):
        temp_file.unlink(missing_ok=True)
