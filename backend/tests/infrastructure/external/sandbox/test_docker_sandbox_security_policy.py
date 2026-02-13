"""Tests for Docker sandbox creation applying security policy."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


class TestDockerSandboxCreateTaskSecurityPolicy:
    """_create_task must apply security policy from policy service."""

    def test_create_task_uses_policy_service_security_options(self) -> None:
        """Security opts, cap_drop, cap_add come from policy service, not literals."""
        # We cannot easily run real Docker, so we verify the code path uses the policy.
        # The policy service is called and its values are passed to containers.run.
        with (
            patch("app.infrastructure.external.sandbox.docker_sandbox.docker.from_env") as docker_mock,
            patch("app.infrastructure.external.sandbox.docker_sandbox.get_settings") as settings_mock,
            patch("app.infrastructure.external.sandbox.docker_sandbox.get_sandbox_security_policy") as policy_mock,
        ):
            settings_mock.return_value = SimpleNamespace(
                sandbox_image="pythinker/pythinker-sandbox",
                sandbox_name_prefix="sandbox",
                sandbox_ttl_minutes=60,
                sandbox_chrome_args="--no-sandbox",
                sandbox_https_proxy=None,
                sandbox_http_proxy=None,
                sandbox_no_proxy=None,
                sandbox_network="pythinker-network",
                sandbox_seccomp_profile="sandbox/seccomp-sandbox.json",
                sandbox_shm_size="2g",
                sandbox_mem_limit="4g",
                sandbox_cpu_limit=1.5,
                sandbox_pids_limit=300,
                sandbox_framework_port=8082,
            )
            policy = MagicMock()
            policy.cap_drop = ["ALL"]
            policy.cap_add_allowlist = ["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"]
            policy.require_no_new_privileges = True
            policy.seccomp_profile_path = "sandbox/seccomp-sandbox.json"
            policy.tmpfs_mounts = [
                "/run:size=50M,nosuid,nodev",
                "/tmp:size=300M,nosuid,nodev",
                "/home/ubuntu/.cache:size=150M,nosuid,nodev",
            ]
            policy_mock.return_value = policy

            client = MagicMock()
            container = MagicMock()
            container.reload = MagicMock()
            container.attrs = {
                "NetworkSettings": {
                    "IPAddress": "172.18.0.5",
                    "Networks": {"pythinker-network": {"IPAddress": "172.18.0.5"}},
                }
            }
            client.containers.run.return_value = container
            docker_mock.return_value = client

            DockerSandbox._create_task()

            policy_mock.assert_called_once()
            call_kwargs = client.containers.run.call_args.kwargs
            assert "no-new-privileges:true" in call_kwargs["security_opt"]
            assert call_kwargs["cap_drop"] == ["ALL"]
            assert set(call_kwargs["cap_add"]) == {"CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"}
            assert "seccomp" in str(call_kwargs["security_opt"]).lower()
