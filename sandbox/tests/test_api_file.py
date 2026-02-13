import pytest
import logging
from pathlib import Path
from fastapi.testclient import TestClient


logger = logging.getLogger(__name__)


@pytest.mark.file_api
def test_upload_file_success(client: TestClient, tmp_path: Path):
    """Test successful file upload"""
    temp_path = tmp_path / "test_upload_unique.txt"

    # Create test file content
    test_content = b"This is test upload content"

    response = client.post(
        "/api/v1/file/upload",
        files={"file": ("test.txt", test_content, "text/plain")},
        data={"path": str(temp_path)},
    )

    assert response.status_code == 200
    data = response.json()

    logger.info(f"Upload response: {data}")

    assert data["success"] is True
    assert "File uploaded successfully" in data["message"]

    # Verify file was created via API
    read_response = client.post("/api/v1/file/read", json={"file": str(temp_path)})
    read_data = read_response.json()
    logger.info(f"Read response: {read_data}")
    assert read_response.status_code == 200
    assert read_data["data"]["content"] == test_content.decode()


@pytest.mark.file_api
def test_download_file_success(client: TestClient, temp_test_file: str):
    """Test successful file download"""
    response = client.get("/api/v1/file/download", params={"path": temp_test_file})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert "attachment" in response.headers.get("content-disposition", "")


@pytest.mark.file_api
def test_download_nonexistent_file(client: TestClient, tmp_path: Path):
    """Test downloading non-existent file"""
    missing_path = tmp_path / "nonexistent.txt"
    response = client.get("/api/v1/file/download", params={"path": str(missing_path)})

    logger.info(f"Download response: {response.status_code}")

    assert response.status_code == 404
