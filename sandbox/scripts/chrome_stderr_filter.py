#!/usr/bin/env python3
"""Filter known benign Chromium stderr noise in sandbox runtime."""

from __future__ import annotations

import re
import sys
import time
from collections.abc import Iterable


SUPPRESSED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"google_apis/gcm/engine/registration_request\.cc:291.*"
        r"(DEPRECATED_ENDPOINT|PHONE_REGISTRATION_ERROR)"
    ),
    re.compile(
        r"google_apis/gcm/engine/mcs_client\.cc:700.*"
        r"Authentication Failed: wrong_secret"
    ),
    re.compile(
        r"google_apis/gcm/engine/mcs_client\.cc:702.*"
        r"Failed to log in to GCM, resetting connection\."
    ),
    re.compile(
        r"dbus/object_proxy\.cc:573.*org\.freedesktop\.DBus\.Properties\.GetAll:"
        r".*UPower.*ServiceUnknown"
    ),
    re.compile(r"GLib-GIO-CRITICAL.*g_settings_schema_source_lookup"),
    # GPU/EGL init failures — expected in headless/no-display containers
    re.compile(r"ui/gl/(angle_platform_impl|egl_util|gl_display)\.cc"),
    re.compile(r"ui/ozone/common/gl_ozone_egl\.cc"),
    re.compile(r"components/viz/service/main/viz_main_impl\.cc.*Exiting GPU process"),
    re.compile(r"^ERR: Display"),
    # Vulkan probe — Chrome probes Vulkan at startup before --disable-vulkan takes effect
    re.compile(r"vkCreateInstance failed"),
    re.compile(r"VK_ERROR_INCOMPATIBLE_DRIVER"),
    # Video capture / on-device model — no GPU/codec hardware in containers
    re.compile(r"Bind context provider failed"),
    re.compile(r"on_device_model.*service disconnect"),
)


def should_suppress(line: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    """Return True when a line matches known benign Chromium noise patterns."""
    return any(pattern.search(line) for pattern in patterns)


def _write_stderr(message: str) -> None:
    sys.stderr.write(message)
    sys.stderr.flush()


def main() -> int:
    suppressed = 0
    last_summary_ts = 0.0
    summary_interval_seconds = 60.0

    for line in sys.stdin:
        if should_suppress(line, SUPPRESSED_PATTERNS):
            suppressed += 1
            now = time.monotonic()
            if (
                suppressed % 50 == 0
                and (now - last_summary_ts) >= summary_interval_seconds
            ):
                _write_stderr(
                    "[chrome-stderr-filter] Suppressed "
                    f"{suppressed} known benign Chromium noise lines\n"
                )
                last_summary_ts = now
            continue
        _write_stderr(line)

    if suppressed > 0:
        _write_stderr(
            "[chrome-stderr-filter] Final suppressed benign Chromium lines: "
            f"{suppressed}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
