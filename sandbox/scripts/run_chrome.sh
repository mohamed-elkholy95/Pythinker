#!/bin/bash
# Chrome wrapper script with filtered stderr.
#
# Runs Chrome headed on Xvfb (:99) with stderr piped through the noise
# filter, using a standard pipeline (not process substitution) to keep
# all processes in the same process group. Combined with supervisord's
# stopasgroup=true, this prevents orphan filter processes on Chrome restart.
#
# Environment:
#   BROWSER_PATH  - Chrome binary (default: /usr/local/bin/chromium)
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

# ── Wait for Xvfb display ────────────────────────────────────────────
while ! xdpyinfo -display :99 >/dev/null 2>&1; do
    echo "Waiting for Xvfb display :99..."
    sleep 0.3
done
export DISPLAY=:99

# ── Chrome binary and flags ──────────────────────────────────────────
CHROME="${BROWSER_PATH:-/usr/local/bin/chromium}"

# Auto-detect browser version for a realistic user-agent string.
# Falls back to the major version only (e.g. "128.0.0.0") when the binary is unavailable.
_CHROME_RAW_VER=$("$CHROME" --version 2>/dev/null | grep -oP '[\d]+\.[\d]+\.[\d]+\.[\d]+' | head -1)
_CHROME_MAJOR=${_CHROME_RAW_VER%%.*}
CHROME_UA_VERSION="${_CHROME_RAW_VER:-${_CHROME_MAJOR:-0}.0.0.0}"

CHROME_FLAGS=(
    --no-sandbox
    --disable-setuid-sandbox
    --window-size=1280,1024
    --start-maximized
    --disable-gpu
    --disable-gpu-sandbox
    --disable-gpu-compositing
    --disable-vulkan
    --enable-unsafe-swiftshader
    # Disable WebGL/WebGL2 — eliminates "GPU stall due to ReadPixels" warnings
    # from SwiftShader's CPU-emulated GL pipeline. The sandbox browser is used
    # for text extraction and page screenshots, not WebGL rendering. Sites fall
    # back to non-WebGL content gracefully.
    --disable-webgl
    --disable-webgl2
    --disable-dev-shm-usage
    --disable-accelerated-jpeg-decoding
    --disable-accelerated-mjpeg-decode
    --disable-accelerated-video-decode
    --disable-features=UseChromeOSDirectVideoDecoder
    --no-first-run
    --no-default-browser-check
    --test-type
    --noerrdialogs
    --disable-session-crashed-bubble
    --hide-crash-restore-bubble
    "--disable-features=WelcomeExperience,SigninPromo,TranslateUI,AudioServiceOutOfProcess,InfiniteSessionRestore,GCMChannelStatusRequest,MediaRouter,DialMediaRouteProvider,PushMessaging,OptimizationHints,AutofillServerCommunication,HardwareMediaKeyHandling,WebGPU"
    "--enable-features=NetworkService,NetworkServiceInProcess"
    --disable-infobars
    --disable-notifications
    --disable-popup-blocking
    --disable-prompt-on-repost
    # NOTE: --disable-component-extensions-with-background-pages removed — it disables
    # Chrome's built-in PDF viewer extension (mhjfbmdgcfjbbpaeojofohoefgiehjai), causing
    # pdf_viewer_wrapper.js / index.css / main.js to fail with net::ERR_FAILED.
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
    --renderer-process-limit=1
    # NOTE: --disable-software-rasterizer removed — it causes black screen on PDF
    # pages and breaks the Chrome built-in PDF viewer rendering pipeline.
    # SwiftShader (--use-gl=swiftshader below) provides the GPU fallback.
    --mute-audio
    --no-pings
    --password-store=basic
    --use-mock-keychain
    --force-color-profile=srgb
    --force-device-scale-factor=1
    --use-gl=swiftshader
    --disable-webrtc
    --disable-blink-features=AutomationControlled
    "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${CHROME_UA_VERSION} Safari/537.36"
    --lang=en-US
    --remote-debugging-address=0.0.0.0
    --remote-debugging-port=8222
    --disable-gcm-client
)

# Append extra args from environment (e.g., from docker-compose CHROME_ARGS)
# shellcheck disable=SC2206
[[ -n "${CHROME_ARGS:-}" ]] && CHROME_FLAGS+=($CHROME_ARGS)

# ── Continuously pin Chrome window to fill the Xvfb display ──────────
# Playwright tab operations (open, close, switch) can reposition or resize
# the Chrome window. This loop runs every 2s and forces all Chromium
# windows back to 0,0 at 1280x1024 so the X11 screencast always captures
# the full browser chrome without dark gaps.
_pin_chrome_window() {
    # Wait for Chrome to appear
    local found=0
    for _ in $(seq 1 30); do
        sleep 1
        if DISPLAY=:99 xdotool search --class chromium 2>/dev/null | head -1 | grep -q .; then
            found=1
            break
        fi
    done
    if [ "$found" -eq 0 ]; then
        echo "[chrome-wrapper] Could not find Chrome window after 30s"
        return 1
    fi

    # Continuous pin loop — 10s interval is sufficient for window drift correction.
    # Reduced from 2s to cut xdotool wake-ups and associated X11 round-trips.
    while true; do
        for wid in $(DISPLAY=:99 xdotool search --class chromium 2>/dev/null); do
            DISPLAY=:99 xdotool windowmove "$wid" 0 0 2>/dev/null
            DISPLAY=:99 xdotool windowsize "$wid" 1280 1024 2>/dev/null
        done
        sleep 10
    done
}
_pin_chrome_window &

# ── Run Chrome with filtered stderr ──────────────────────────────────
# fd 3 = original stdout (preserved for Chrome)
# Chrome's stderr → pipe → filter → stderr
# Bash stays as process group leader for clean signal propagation.
exec 3>&1
"$CHROME" "${CHROME_FLAGS[@]}" 2>&1 1>&3 3>&- \
    | python3 /app/scripts/chrome_stderr_filter.py >&2 3>&-

chrome_exit_code=${PIPESTATUS[0]:-0}
stderr_filter_exit_code=${PIPESTATUS[1]:-0}

if [ "$chrome_exit_code" -ne 0 ]; then
    echo "[chrome-wrapper] Chrome exited with code ${chrome_exit_code}; collecting diagnostics..."
    if [ "$chrome_exit_code" -eq 137 ]; then
        echo "[chrome-wrapper] Exit 137 indicates SIGKILL (often OOM kill or external process kill)."
    fi

    if [ -r /sys/fs/cgroup/memory.events ]; then
        echo "[chrome-wrapper] cgroup memory.events:"
        cat /sys/fs/cgroup/memory.events
    elif [ -r /sys/fs/cgroup/memory/memory.oom_control ]; then
        echo "[chrome-wrapper] cgroup v1 memory.oom_control:"
        cat /sys/fs/cgroup/memory/memory.oom_control
        if [ -r /sys/fs/cgroup/memory/memory.failcnt ]; then
            echo "[chrome-wrapper] cgroup v1 memory.failcnt:"
            cat /sys/fs/cgroup/memory/memory.failcnt
        fi
    fi

    if [ -r /sys/fs/cgroup/memory.current ]; then
        echo "[chrome-wrapper] cgroup memory.current:"
        cat /sys/fs/cgroup/memory.current
    fi
    if [ -r /sys/fs/cgroup/memory.max ]; then
        echo "[chrome-wrapper] cgroup memory.max:"
        cat /sys/fs/cgroup/memory.max
    fi

    if command -v free >/dev/null 2>&1; then
        echo "[chrome-wrapper] free -m:"
        free -m
    fi
    if command -v ps >/dev/null 2>&1; then
        echo "[chrome-wrapper] chrome/chromium process snapshot:"
        ps -eo pid,ppid,pmem,rss,args | grep -E "chrome|chromium" | grep -v grep || true
    fi
fi

if [ "$stderr_filter_exit_code" -ne 0 ]; then
    echo "[chrome-wrapper] chrome_stderr_filter exited with code ${stderr_filter_exit_code}."
fi

exit "$chrome_exit_code"
