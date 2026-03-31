#!/usr/bin/env bash
# Launches x11vnc against Xvfb :99. Keep flags in this file (not only inline in
# supervisord.conf) so ENABLE_VNC / ncache behavior is obvious and easy to verify
# inside the container: `tr '\0' ' ' < /proc/$(pgrep -f x11vnc)/cmdline`.
#
# Client-side -ncache expands the RFB to W×(n+1)×H (see man x11vnc), which breaks
# noVNC scaling (~1280×12288). -nonc is equivalent to -ncache 0 and must win over
# any distro defaults.

set -euo pipefail

if [ "${ENABLE_VNC:-}" != "1" ] && [ "${ENABLE_VNC:-}" != "true" ]; then
  echo "VNC disabled (set ENABLE_VNC=1 to enable)"
  exit 0
fi

while ! xdpyinfo -display :99 >/dev/null 2>&1; do
  sleep 0.2
done

# -nonc first: disable ncache before any other option might interact with it.
exec x11vnc -nonc \
  -display :99 \
  -forever -nopw -shared -rfbport 5900 \
  -xkb -noxrecord -noxfixes -noxdamage -no6 \
  -wait 100 -defer 50 -nap -threads
