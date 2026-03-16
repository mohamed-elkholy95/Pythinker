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


def test_buildkit_startup_warnings_are_ignored() -> None:
    monitor = DockerLogMonitor()
    warning_line = 'level=warning msg="using host network as the default"'

    with patch("app.infrastructure.observability.docker_log_monitor.logger.warning") as log_warning:
        monitor._process_line("buildx_buildkit_charming_jang0", warning_line)
        log_warning.assert_not_called()


def test_chrome_upower_dbus_errors_are_ignored() -> None:
    monitor = DockerLogMonitor()
    dbus_line = (
        "[100:193:0301/181221.053310:ERROR:object_proxy.cc(576)] Failed to call method: "
        "org.freedesktop.DBus.Properties.Get: object_path= /org/freedesktop/UPower: "
        "org.freedesktop.DBus.Error.ServiceUnknown: The name org.freedesktop.UPower was not provided by any .service files"
    )

    with patch("app.infrastructure.observability.docker_log_monitor.logger.error") as log_error:
        monitor._process_line("sandbox", dbus_line)
        log_error.assert_not_called()
