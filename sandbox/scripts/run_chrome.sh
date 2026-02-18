#!/bin/bash
# Chrome wrapper script with filtered stderr.
#
# Runs Chrome headless with stderr piped through the noise filter, using
# a standard pipeline (not process substitution) to keep all processes
# in the same process group. Combined with supervisord's stopasgroup=true,
# this prevents orphan filter processes on Chrome restart.
#
# Environment:
#   BROWSER_PATH  - Chrome binary (default: /opt/chrome-for-testing/chrome)
#   CHROME_ARGS   - Additional Chrome flags (space-separated)

set -uo pipefail

# ── Wait for D-Bus session socket ─────────────────────────────────────
while [ ! -S /tmp/runtime-ubuntu/dbus-session ]; do
    echo "Waiting for dbus session..."
    sleep 0.2
done

mkdir -p /tmp/runtime-ubuntu /tmp/runtime-ubuntu/dconf 2>/dev/null || true

export XDG_RUNTIME_DIR=/tmp/runtime-ubuntu
export DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/runtime-ubuntu/dbus-session
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/tmp/runtime-ubuntu/dbus-session
export GSETTINGS_BACKEND=memory

sleep 1

# ── Chrome binary and flags ──────────────────────────────────────────
CHROME="${BROWSER_PATH:-/opt/chrome-for-testing/chrome}"

CHROME_FLAGS=(
    --headless=new
    --no-sandbox
    --disable-setuid-sandbox
    --window-size=1280,1024
    --disable-gpu
    --disable-gpu-sandbox
    --disable-vulkan
    --disable-accelerated-jpeg-decoding
    --disable-accelerated-mjpeg-decode
    --disable-accelerated-video-decode
    --no-first-run
    --no-default-browser-check
    --test-type
    --noerrdialogs
    --disable-session-crashed-bubble
    --hide-crash-restore-bubble
    "--disable-features=WelcomeExperience,SigninPromo,TranslateUI,AudioServiceOutOfProcess,InfiniteSessionRestore,GCMChannelStatusRequest,MediaRouter,DialMediaRouteProvider,PushMessaging,OptimizationHints,AutofillServerCommunication"
    "--enable-features=NetworkService,NetworkServiceInProcess"
    --disable-infobars
    --disable-notifications
    --disable-popup-blocking
    --disable-prompt-on-repost
    --disable-extensions
    --disable-component-extensions-with-background-pages
    --disable-component-update
    --disable-component-cloud-policy
    --disable-background-networking
    --disable-background-timer-throttling
    --disable-backgrounding-occluded-windows
    --disable-breakpad
    --disable-client-side-phishing-detection
    --disable-default-apps
    --disable-domain-reliability
    --disable-hang-monitor
    --disable-ipc-flooding-protection
    --disable-renderer-backgrounding
    --disable-sync
    --disable-translate
    --metrics-recording-only
    --mute-audio
    --no-pings
    --password-store=basic
    --use-mock-keychain
    --force-color-profile=srgb
    --force-device-scale-factor=1
    --disable-blink-features=AutomationControlled
    "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    --lang=en-US
    --remote-debugging-address=0.0.0.0
    --remote-debugging-port=8222
    --disable-gcm-client
)

# Append extra args from environment (e.g., from docker-compose CHROME_ARGS)
# shellcheck disable=SC2206
[[ -n "${CHROME_ARGS:-}" ]] && CHROME_FLAGS+=($CHROME_ARGS)

# ── Run Chrome with filtered stderr ──────────────────────────────────
# fd 3 = original stdout (preserved for Chrome)
# Chrome's stderr → pipe → filter → stderr
# Bash stays as process group leader for clean signal propagation.
exec 3>&1
"$CHROME" "${CHROME_FLAGS[@]}" 2>&1 1>&3 3>&- \
    | python3 /app/scripts/chrome_stderr_filter.py >&2 3>&-
