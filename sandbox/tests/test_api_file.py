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


@pytest.mark.file_api
def test_list_directory_success(client: TestClient, tmp_path: Path):
    """Test listing files in a directory."""
    file_a = tmp_path / "alpha.txt"
    file_b = tmp_path / "beta.txt"

    client.post("/api/v1/file/write", json={"file": str(file_a), "content": "a"})
    client.post("/api/v1/file/write", json={"file": str(file_b), "content": "b"})

    response = client.post("/api/v1/file/list", json={"path": str(tmp_path)})
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    names = {entry["name"] for entry in payload["data"]["entries"]}
    assert {"alpha.txt", "beta.txt"}.issubset(names)


@pytest.mark.file_api
def test_delete_file_success(client: TestClient, tmp_path: Path):
    """Test deleting an existing file."""
    target = tmp_path / "to_delete.txt"
    client.post("/api/v1/file/write", json={"file": str(target), "content": "remove me"})

    delete_response = client.post("/api/v1/file/delete", json={"path": str(target)})
    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert delete_payload["success"] is True
    assert delete_payload["data"]["deleted"] is True

    read_response = client.post("/api/v1/file/read", json={"file": str(target)})
    assert read_response.status_code == 404
