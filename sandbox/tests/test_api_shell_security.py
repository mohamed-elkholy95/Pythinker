import pytest
from conftest import BASE_URL


@pytest.mark.shell_api
def test_shell_blocks_sudo(client):
    response = client.post(f"{BASE_URL}/api/v1/shell/exec", json={
        "exec_dir": "/tmp",
        "command": "sudo ls"
    })

    assert response.status_code == 400


@pytest.mark.shell_api
def test_shell_blocks_dangerous_command(client):
    response = client.post(f"{BASE_URL}/api/v1/shell/exec", json={
        "exec_dir": "/tmp",
        "command": "rm -rf /"
    })

    assert response.status_code == 400


@pytest.mark.shell_api
def test_shell_blocks_invalid_exec_dir(client):
    response = client.post(f"{BASE_URL}/api/v1/shell/exec", json={
        "exec_dir": "/etc",
        "command": "ls"
    })

    assert response.status_code == 400
