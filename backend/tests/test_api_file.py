"""
Integration tests for file upload/download API endpoints.

These tests require:
1. A running backend API
2. Password auth provider (for registration to create authenticated sessions)
3. Files endpoint requires authentication

Tests are skipped if these conditions aren't met.
"""
import io
import logging
import os
import tempfile

import pytest
import requests

from conftest import BASE_URL

logger = logging.getLogger(__name__)

# Check if backend API is available and supports registration
def _get_auth_config():
    """Get auth configuration from the API."""
    try:
        response = requests.get(f"{BASE_URL}/auth/status", timeout=2.0)
        if response.status_code == 200:
            data = response.json().get("data", {})
            return {
                "api_available": True,
                "auth_provider": data.get("auth_provider", "unknown"),
            }
    except Exception:
        pass
    return {"api_available": False, "auth_provider": None}

_AUTH_CONFIG = _get_auth_config()

# Files API requires authentication, which requires registration to work
# Skip all tests if API is not available OR if registration is not supported
pytestmark = pytest.mark.skipif(
    not _AUTH_CONFIG["api_available"] or _AUTH_CONFIG.get("auth_provider") != "password",
    reason=f"Backend API not running or doesn't support registration (provider: {_AUTH_CONFIG.get('auth_provider')})"
)


@pytest.fixture
def authenticated_client(client):
    """Create an authenticated requests session for file operations"""
    import uuid

    # Register a unique user for this test session
    unique_suffix = str(uuid.uuid4())[:8]
    user_data = {
        "fullname": f"File Test User {unique_suffix}",
        "password": "password123",
        "email": f"filetest_{unique_suffix}@example.com"
    }

    # Try to register
    register_url = f"{BASE_URL}/auth/register"
    register_response = client.post(register_url, json=user_data)

    if register_response.status_code == 200:
        auth_data = register_response.json()["data"]
        access_token = auth_data["access_token"]
    else:
        # Try login if registration failed
        login_url = f"{BASE_URL}/auth/login"
        login_response = client.post(login_url, json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        if login_response.status_code == 200:
            auth_data = login_response.json()["data"]
            access_token = auth_data["access_token"]
        else:
            pytest.skip("Could not authenticate for file tests")
            return client

    # Set authorization header for all subsequent requests
    client.headers.update({"Authorization": f"Bearer {access_token}"})
    return client


@pytest.fixture
def sample_file_content():
    """Create sample file content for testing"""
    return b"This is a test file content for API testing."


@pytest.fixture
def sample_text_file(sample_file_content):
    """Create a temporary text file for testing"""
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
        f.write(sample_file_content)
        f.flush()
        yield f.name
    # Cleanup
    if os.path.exists(f.name):
        os.unlink(f.name)


def test_upload_file_success(authenticated_client, sample_text_file):
    """Test successful file upload"""
    url = f"{BASE_URL}/files"

    with open(sample_text_file, 'rb') as f:
        files = {'file': ('test_file.txt', f, 'text/plain')}
        response = authenticated_client.post(url, files=files)

    logger.info(f"Upload file response: {response.status_code} - {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data['code'] == 0
    assert 'data' in data
    assert 'file_id' in data['data']
    assert data['data']['filename'] == 'test_file.txt'
    assert data['data']['size'] > 0
    assert 'upload_date' in data['data']


def test_upload_file_without_file(authenticated_client):
    """Test upload without providing file"""
    url = f"{BASE_URL}/files"
    response = authenticated_client.post(url)

    logger.info(f"Upload without file response: {response.status_code} - {response.text}")
    assert response.status_code == 422  # Validation error


def test_upload_empty_file(authenticated_client):
    """Test upload empty file"""
    url = f"{BASE_URL}/files"

    # Create empty file
    empty_file = io.BytesIO(b"")
    files = {'file': ('empty.txt', empty_file, 'text/plain')}
    response = authenticated_client.post(url, files=files)

    logger.info(f"Upload empty file response: {response.status_code} - {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data['code'] == 0
    assert data['data']['size'] == 0


def test_get_file_info_success(authenticated_client, sample_text_file):
    """Test getting file information"""
    # First upload a file
    upload_url = f"{BASE_URL}/files"
    with open(sample_text_file, 'rb') as f:
        files = {'file': ('info_test.txt', f, 'text/plain')}
        upload_response = authenticated_client.post(upload_url, files=files)

    logger.info(f"Upload for info test response: {upload_response.status_code} - {upload_response.text}")
    file_id = upload_response.json()['data']['file_id']

    # Get file info
    info_url = f"{BASE_URL}/files/{file_id}/info"
    response = authenticated_client.get(info_url)

    logger.info(f"Get file info response: {response.status_code} - {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data['code'] == 0
    assert data['data']['file_id'] == file_id
    assert data['data']['filename'] == 'info_test.txt'
    assert data['data']['content_type'] == 'text/plain'
    assert data['data']['size'] > 0
    assert 'upload_date' in data['data']


def test_get_file_info_not_found(authenticated_client):
    """Test getting info for non-existent file"""
    fake_file_id = "507f1f77bcf86cd799439011"  # Valid ObjectId format
    url = f"{BASE_URL}/files/{fake_file_id}/info"
    response = authenticated_client.get(url)

    logger.info(f"Get file info not found response: {response.status_code} - {response.text}")
    assert response.status_code == 404


def test_download_file_success(authenticated_client, sample_text_file, sample_file_content):
    """Test successful file download"""
    # First upload a file
    upload_url = f"{BASE_URL}/files"
    with open(sample_text_file, 'rb') as f:
        files = {'file': ('download_test.txt', f, 'text/plain')}
        upload_response = authenticated_client.post(upload_url, files=files)

    logger.info(f"Upload for download test response: {upload_response.status_code} - {upload_response.text}")
    upload_data = upload_response.json()['data']

    # Download file using the signed URL from the upload response
    # The file_url contains the signature required for download
    file_url = upload_data.get('file_url', f"/api/v1/files/{upload_data['file_id']}")
    # file_url is relative, we need to construct full URL
    download_url = f"http://localhost:8000{file_url}"
    response = authenticated_client.get(download_url)

    logger.info(f"Download file response: {response.status_code} - Content length: {len(response.content)}")
    assert response.status_code == 200
    assert response.content == sample_file_content
    assert 'Content-Disposition' in response.headers
    assert 'download_test.txt' in response.headers['Content-Disposition']


def test_download_file_not_found(authenticated_client):
    """Test downloading non-existent file"""
    fake_file_id = "507f1f77bcf86cd799439011"  # Valid ObjectId format
    # Provide a fake signature to pass signature validation, then get 404 for missing file
    url = f"{BASE_URL}/files/{fake_file_id}?signature=fakesig&expires=9999999999"
    response = authenticated_client.get(url)

    logger.info(f"Download file not found response: {response.status_code} - {response.text}")
    # API returns 401 with invalid signature or 404 if signature validation is bypassed
    assert response.status_code in [401, 404]


def test_delete_file_success(authenticated_client, sample_text_file):
    """Test successful file deletion"""
    # First upload a file
    upload_url = f"{BASE_URL}/files"
    with open(sample_text_file, 'rb') as f:
        files = {'file': ('delete_test.txt', f, 'text/plain')}
        upload_response = authenticated_client.post(upload_url, files=files)

    file_id = upload_response.json()['data']['file_id']

    # Delete file
    delete_url = f"{BASE_URL}/files/{file_id}"
    response = authenticated_client.delete(delete_url)

    logger.info(f"Delete file response: {response.status_code} - {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data['code'] == 0

    # Verify file is deleted by trying to get info
    info_url = f"{BASE_URL}/files/{file_id}/info"
    info_response = authenticated_client.get(info_url)
    logger.info(f"Verify deletion response: {info_response.status_code} - {info_response.text}")
    assert info_response.status_code == 404


def test_delete_file_not_found(authenticated_client):
    """Test deleting non-existent file"""
    fake_file_id = "507f1f77bcf86cd799439011"  # Valid ObjectId format
    url = f"{BASE_URL}/files/{fake_file_id}"
    response = authenticated_client.delete(url)

    logger.info(f"Delete file not found response: {response.status_code} - {response.text}")
    assert response.status_code == 404


def test_upload_large_file(authenticated_client):
    """Test uploading a larger file"""
    # Create a 1MB file content
    large_content = b"A" * (1024 * 1024)  # 1MB

    url = f"{BASE_URL}/files"
    files = {'file': ('large_file.txt', io.BytesIO(large_content), 'text/plain')}
    response = authenticated_client.post(url, files=files)

    assert response.status_code == 200
    data = response.json()
    assert data['code'] == 0
    assert data['data']['size'] == 1024 * 1024


def test_upload_binary_file(authenticated_client):
    """Test uploading a binary file"""
    # Create binary content
    binary_content = bytes(range(256))  # 0-255 bytes

    url = f"{BASE_URL}/files"
    files = {'file': ('binary_file.bin', io.BytesIO(binary_content), 'application/octet-stream')}
    response = authenticated_client.post(url, files=files)

    assert response.status_code == 200
    data = response.json()
    assert data['code'] == 0
    assert data['data']['size'] == 256

    # Download and verify content using signed URL
    file_url = data['data'].get('file_url', f"/api/v1/files/{data['data']['file_id']}")
    download_url = f"http://localhost:8000{file_url}"
    download_response = authenticated_client.get(download_url)

    assert download_response.status_code == 200
    assert download_response.content == binary_content

