#!/usr/bin/env python3
"""Hide the X11 cursor using the XFIXES extension.

Calls XFixesHideCursor() and keeps the X11 connection open indefinitely.
XFixesHideCursor is per-client — if the connection closes, the cursor
reappears.  This process sleeps forever to hold the connection.

Uses ctypes to call libXfixes directly.  No additional Python packages
required — libxfixes3 and libX11 are already present in the sandbox image
(runtime dependencies of Chromium).

Usage:
    python3 hide_x11_cursor.py            # uses DISPLAY env var
    python3 hide_x11_cursor.py :99        # explicit display
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import signal
import sys
import time


def hide_cursor(display_name: str | None = None) -> bool:
    """Hide the X11 cursor and keep the connection open.

    This function blocks forever (sleeping) to maintain the X11 connection.
    The cursor stays hidden as long as this process is alive.
    """
    display_name = display_name or os.environ.get("DISPLAY", ":99")
    display_bytes = display_name.encode() if display_name else None

    # Load shared libraries
    try:
        libx11_path = ctypes.util.find_library("X11")
        libxfixes_path = ctypes.util.find_library("Xfixes")

        if not libx11_path or not libxfixes_path:
            libx11_path = libx11_path or "libX11.so.6"
            libxfixes_path = libxfixes_path or "libXfixes.so.3"

        libx11 = ctypes.cdll.LoadLibrary(libx11_path)
        libxfixes = ctypes.cdll.LoadLibrary(libxfixes_path)
    except OSError as e:
        print(
            f"[hide_cursor] Failed to load X11/Xfixes libraries: {e}", file=sys.stderr
        )
        return False

    # XOpenDisplay
    libx11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    libx11.XOpenDisplay.restype = ctypes.c_void_p

    display = libx11.XOpenDisplay(display_bytes)
    if not display:
        print(f"[hide_cursor] Cannot open display {display_name}", file=sys.stderr)
        return False

    # XDefaultRootWindow
    libx11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    libx11.XDefaultRootWindow.restype = ctypes.c_ulong

    root = libx11.XDefaultRootWindow(display)

    # XFixesHideCursor(Display*, Window)
    libxfixes.XFixesHideCursor.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    libxfixes.XFixesHideCursor.restype = None

    libxfixes.XFixesHideCursor(display, root)

    # Flush to apply immediately
    libx11.XFlush.argtypes = [ctypes.c_void_p]
    libx11.XFlush.restype = ctypes.c_int
    libx11.XFlush(display)

    print(
        f"[hide_cursor] X11 cursor hidden on {display_name} (holding connection open)"
    )

    # Keep connection alive — XFixesHideCursor is per-client.
    # If we close the display or exit, the cursor reappears.
    # Sleep forever with minimal overhead (~0 CPU).
    def _shutdown(signum: int, frame: object) -> None:
        # Graceful shutdown: close display, let cursor reappear
        libx11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        libx11.XCloseDisplay.restype = ctypes.c_int
        libx11.XCloseDisplay(display)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while True:
        time.sleep(86400)  # Sleep 24h per iteration (near-zero overhead)


if __name__ == "__main__":
    display_arg = sys.argv[1] if len(sys.argv) > 1 else None
    hide_cursor(display_arg)
