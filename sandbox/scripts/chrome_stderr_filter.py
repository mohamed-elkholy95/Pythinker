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
    # UPower D-Bus errors — UPower is not present in Docker containers.
    # Chrome probes it via 3 separate calls (Properties.Get, GetDisplayDevice,
    # EnumerateDevices) all logged via object_proxy.cc at varying line numbers
    # depending on Chrome version. Match by content rather than line number.
    re.compile(r"object_proxy\.cc.*UPower.*ServiceUnknown"),
    re.compile(r"GLib-GIO-CRITICAL.*g_settings_schema_source_lookup"),
    # GPU/EGL init failures — expected in headless/no-display containers
    re.compile(r"ui/gl/(angle_platform_impl|egl_util|gl_display)\.cc"),
    re.compile(r"ui/ozone/common/gl_ozone_egl\.cc"),
    re.compile(r"components/viz/service/main/viz_main_impl\.cc.*Exiting GPU process"),
    re.compile(r"^ERR: Display"),
    # Vulkan probe — Chrome probes Vulkan at startup before --disable-vulkan takes effect
    re.compile(r"vkCreateInstance"),
    re.compile(r"VK_ERROR_INCOMPATIBLE_DRIVER"),
    re.compile(r"CheckVkSuccessImpl"),
    # GPU blocklist — no GPU adapter in headless containers
    re.compile(r"gpu_blocklist\.cc.*Unable to get gpu adapter"),
    # GPU shared image compositor — no real GPU in containers
    re.compile(r"SharedImageManager::ProduceMemory"),
    # Video capture / on-device model — no GPU/codec hardware in containers
    re.compile(r"Bind context provider failed"),
    re.compile(r"on_device_model.*service disconnect"),
    # ALSA/audio probing noise in containerized Chrome (no sound card attached)
    re.compile(r"^ALSA lib "),
    re.compile(r"alsa_util\.cc[:(]\d+[)\]].*PcmOpen"),
    # Transient SSL handshake noise from blocked/ephemeral third-party subresources
    # and Chrome background connectivity checks (CRLSet, component updates).
    # -101: connection reset; -201: certificate verification or similar in container.
    re.compile(r"ssl_client_socket_impl\.cc.*handshake failed.*net_error -20[01]"),
    re.compile(r"ssl_client_socket_impl\.cc.*handshake failed.*net_error -10[01]"),
    # Long compositor animations on heavy pages — benign in automation/screencast use.
    re.compile(r"compositor_animation_observer\.cc.*CompositorAnimationObserver is active for too long"),
    # STUN server DNS resolution failures — WebRTC NAT traversal is not needed
    # in the sandbox (CDP screencast does not use WebRTC).
    re.compile(r"socket_manager\.cc.*Failed to resolve address for stun"),
    # GPU stall / ReadPixels — SwiftShader CPU-emulated GL pipeline sync.
    # Triggered by any residual WebGL or compositor glReadPixels calls.
    # "GL_CLOSE_PATH_NV" is an NVIDIA driver message category, not an error.
    re.compile(r"gl_utils\.cc.*GPU stall due to ReadPixels"),
    # Dawn/WebGPU adapter limit warnings — Dawn probes GPU adapter limits at
    # startup even when WebGPU is unused; artificially reduced limits are normal
    # for SwiftShader/software rendering.
    re.compile(r"maxDynamic\w+BuffersPerPipelineLayout artificially reduced"),
    # GCM registration quota — Google Cloud Messaging quota exceeded in
    # containerized Chromium with no valid GCM credentials.
    re.compile(r"registration_request\.cc.*QUOTA_EXCEEDED"),
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
