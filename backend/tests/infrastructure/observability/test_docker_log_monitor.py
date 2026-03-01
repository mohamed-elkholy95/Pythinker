from unittest.mock import patch

from app.infrastructure.observability.docker_log_monitor import DockerLogMonitor


def test_mongodb_info_logs_are_ignored() -> None:
    monitor = DockerLogMonitor()
    mongodb_info_line = (
        '{"t":{"$date":"2026-03-01T18:12:18.351+00:00"},'
        '"s":"I","c":"STORAGE","id":22315,"ctx":"initandlisten","msg":"Opening WiredTiger"}'
    )

    with patch("app.infrastructure.observability.docker_log_monitor.logger.error") as log_error:
        monitor._process_line("mongodb", mongodb_info_line)
        log_error.assert_not_called()


def test_mongodb_error_logs_still_emit_alerts() -> None:
    monitor = DockerLogMonitor()
    mongodb_error_line = (
        '{"t":{"$date":"2026-03-01T18:12:18.351+00:00"},"s":"E","c":"STORAGE","msg":"failed to open file"}'
    )

    with patch("app.infrastructure.observability.docker_log_monitor.logger.error") as log_error:
        monitor._process_line("mongodb", mongodb_error_line)
        log_error.assert_called_once()


def test_non_json_warning_lines_still_work() -> None:
    monitor = DockerLogMonitor()
    warn_line = "connection refused to upstream service"

    with patch("app.infrastructure.observability.docker_log_monitor.logger.error") as log_error:
        monitor._process_line("backend", warn_line)
        log_error.assert_called_once()
        args, _kwargs = log_error.call_args
        assert "connection refused" in args[0]
