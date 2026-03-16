from __future__ import annotations

import subprocess
from pathlib import Path


def _run_filter(input_text: str) -> subprocess.CompletedProcess[str]:
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "chrome_stderr_filter.py"
    )
    return subprocess.run(
        ["python3", str(script_path)],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def test_chrome_stderr_filter_suppresses_known_benign_noise() -> None:
    noisy_lines = [
        "[20:192:0213/191002.294792:ERROR:google_apis/gcm/engine/registration_request.cc:291] "
        "Registration response error message: DEPRECATED_ENDPOINT",
        "[20:192:0213/191002.493386:ERROR:google_apis/gcm/engine/mcs_client.cc:700]   "
        "Error code: 401  Error message: Authentication Failed: wrong_secret",
        "[20:20:0213/191000.120629:ERROR:dbus/object_proxy.cc:573] Failed to call method: "
        "org.freedesktop.DBus.Properties.GetAll: object_path= /org/freedesktop/UPower/devices/DisplayDevice: "
        "org.freedesktop.DBus.Error.ServiceUnknown: The name org.freedesktop.UPower was not provided by any .service files",
        "ALSA lib confmisc.c:855:(parse_card) cannot find card '0'",
        "[1118:1118:0303/155138.479711:ERROR:alsa_util.cc(204)] PcmOpen: default,No such file or directory",
        "[881:889:0303/155139.363044:ERROR:ssl_client_socket_impl.cc(878)] handshake failed; returned -1, SSL error code 1, net_error -101",
    ]
    actionable_line = (
        "[123:456:0213/191200.000000:ERROR:net/socket.cc:42] Actionable network failure"
    )
    proc = _run_filter("\n".join([*noisy_lines, actionable_line]) + "\n")

    assert proc.returncode == 0
    assert actionable_line in proc.stderr
    for line in noisy_lines:
        assert line not in proc.stderr
    assert (
        "[chrome-stderr-filter] Final suppressed benign Chromium lines: 6"
        in proc.stderr
    )
    assert proc.stdout == ""
