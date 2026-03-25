#!/usr/bin/env bash
# =============================================================================
# Pythinker Autonomous Dev Cycle — Runner Script (v4)
#
# Invoked by crontab every 2 hours. Launches Claude Code in headless mode
# with the full v4 cycle prompt.
#
# Usage:
#   ./.pythinker-cron/run-cycle.sh          # Normal run
#   ./.pythinker-cron/run-cycle.sh --dry    # Print what would run, don't execute
#
# Logs: /tmp/pythinker-cron-YYYYMMDD-HHMM.log (rotated: keeps last 48)
# Lock: .pythinker-cron.lock (prevents concurrent runs)
# =============================================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMPT_FILE="$PROJECT_DIR/.pythinker-cron/cycle-prompt.md"
RULES_FILE="$PROJECT_DIR/.pythinker-cron/rules.md"
STATE_FILE="$PROJECT_DIR/.pythinker-cron-state.json"
LOCK_FILE="$PROJECT_DIR/.pythinker-cron.lock"
LOG_DIR="/tmp"
LOG_PREFIX="pythinker-cron"
LOG_FILE="$LOG_DIR/${LOG_PREFIX}-$(date +%Y%m%d-%H%M).log"
MAX_LOGS=48  # Keep last 48 logs (4 days at 2h intervals)

CLAUDE_BIN="$HOME/.local/bin/claude"
CONDA_BIN="$HOME/miniconda3/bin/conda"

# Max runtime: 2h 10m (130 min) — hard kill if Claude hangs
MAX_RUNTIME_SEC=7800

# ── Functions ─────────────────────────────────────────────────────────────────

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

cleanup() {
    rm -f "$LOCK_FILE"
    log "Lock released. Cycle runner exiting."
}

rotate_logs() {
    # Keep only the last $MAX_LOGS log files
    local count
    count=$(find "$LOG_DIR" -maxdepth 1 -name "${LOG_PREFIX}-*.log" -type f | wc -l)
    if (( count > MAX_LOGS )); then
        find "$LOG_DIR" -maxdepth 1 -name "${LOG_PREFIX}-*.log" -type f -printf '%T@ %p\n' \
            | sort -n \
            | head -n $(( count - MAX_LOGS )) \
            | cut -d' ' -f2- \
            | xargs rm -f
    fi
}

# ── Pre-flight ────────────────────────────────────────────────────────────────

# Dry-run mode
if [[ "${1:-}" == "--dry" ]]; then
    echo "DRY RUN — would execute:"
    echo "  cd $PROJECT_DIR"
    echo "  timeout ${MAX_RUNTIME_SEC}s $CLAUDE_BIN -p \"\$(cat $PROMPT_FILE)\" --dangerously-skip-permissions"
    echo "  Log: $LOG_FILE"
    exit 0
fi

# Ensure log exists
touch "$LOG_FILE"
log "=== Pythinker Dev Cycle v4 — Starting ==="
log "Project: $PROJECT_DIR"

# Rotate old logs
rotate_logs

# Check Claude binary
if [[ ! -x "$CLAUDE_BIN" ]]; then
    log "ERROR: Claude binary not found at $CLAUDE_BIN"
    exit 1
fi

# Check prompt file
if [[ ! -f "$PROMPT_FILE" ]]; then
    log "ERROR: Cycle prompt not found at $PROMPT_FILE"
    exit 1
fi

# Check rules file
if [[ ! -f "$RULES_FILE" ]]; then
    log "WARNING: Rules file not found at $RULES_FILE"
fi

# Lock check (the prompt also checks, but this prevents even launching Claude)
if [[ -f "$LOCK_FILE" ]]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "unknown")
    LOCK_AGE_MIN=0
    if [[ -f "$LOCK_FILE" ]]; then
        LOCK_AGE_SEC=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || date +%s) ))
        LOCK_AGE_MIN=$(( LOCK_AGE_SEC / 60 ))
    fi

    # Stale lock detection: if lock is older than MAX_RUNTIME + 10 min, it's stale
    if (( LOCK_AGE_SEC > MAX_RUNTIME_SEC + 600 )); then
        log "WARNING: Stale lock detected (age: ${LOCK_AGE_MIN}m, PID: $LOCK_PID). Removing."
        rm -f "$LOCK_FILE"
    else
        log "ABORT: Lock file exists (PID: $LOCK_PID, age: ${LOCK_AGE_MIN}m). Another cycle is running."
        exit 0  # Exit 0 — not an error, just skipping
    fi
fi

# Create lock with our PID
echo $$ > "$LOCK_FILE"
trap cleanup EXIT  # Always remove lock on exit

# ── Environment Setup ─────────────────────────────────────────────────────────

# Ensure PATH includes conda, Claude, and standard tools
export PATH="$HOME/.local/bin:$HOME/miniconda3/bin:$HOME/.bun/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# NVM (for bun/node if needed by Claude)
export NVM_DIR="$HOME/.nvm"
[[ -s "$NVM_DIR/nvm.sh" ]] && source "$NVM_DIR/nvm.sh" 2>/dev/null

# Conda init (so `conda activate` works inside Claude's bash calls)
eval "$($CONDA_BIN shell.bash hook 2>/dev/null)" 2>/dev/null || true

# ── Execute ───────────────────────────────────────────────────────────────────

log "Launching Claude Code (timeout: ${MAX_RUNTIME_SEC}s)..."
cd "$PROJECT_DIR"

# Read prompt into variable (avoids subshell issues with timeout)
PROMPT=$(cat "$PROMPT_FILE")
RUN_TS=$(date +%s)
RUN_UUID=$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex)
PY
)
RUN_TAG="cron-cycle-${RUN_TS}-${RUN_UUID}"
export PYTHINKER_CRON_RUN_TAG="$RUN_TAG"
export PYTHINKER_CRON_LOG_FILE="$LOG_FILE"

log "Run tag: $RUN_TAG"

# Run Claude in headless mode with hard timeout
set +e  # Don't exit on Claude failure
timeout "$MAX_RUNTIME_SEC" "$CLAUDE_BIN" \
    -p "$PROMPT" \
    --append-system-prompt "Autonomous cron run tag: $RUN_TAG. Every canary/live session created during this run must be fresh and uniquely attributable to this tag. Any reused session id, accidental attachment to an older session, or stop/cancel of the fresh canary session is a hard failure and must be reported." \
    --dangerously-skip-permissions \
    --output-format text \
    >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
set -e

if grep -q "SESSION_REUSE_BUG:\|returned existing session_id=\|attached to a different session id\|cancelled/stopped session" "$LOG_FILE" 2>/dev/null; then
    log "Detected session lifecycle failure markers in log; overriding exit code to failure"
    EXIT_CODE=42
fi

# ── Post-run ──────────────────────────────────────────────────────────────────

if (( EXIT_CODE == 0 )); then
    log "=== Cycle completed successfully ==="
elif (( EXIT_CODE == 124 )); then
    log "=== Cycle TIMED OUT after ${MAX_RUNTIME_SEC}s ==="
    # Update state file consecutive errors
    if [[ -f "$STATE_FILE" ]]; then
        python3 -c "
import json, sys
with open('$STATE_FILE') as f:
    state = json.load(f)
state['consecutiveErrors'] = state.get('consecutiveErrors', 0) + 1
state['lastRunStatus'] = 'timeout'
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
print(f'consecutiveErrors: {state[\"consecutiveErrors\"]}')
" 2>/dev/null || true
    fi
else
    log "=== Cycle FAILED with exit code $EXIT_CODE ==="
    if [[ -f "$STATE_FILE" ]]; then
        python3 -c "
import json
with open('$STATE_FILE') as f:
    state = json.load(f)
state['consecutiveErrors'] = state.get('consecutiveErrors', 0) + 1
state['lastRunStatus'] = 'failed'
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
print(f'consecutiveErrors: {state[\"consecutiveErrors\"]}')
" 2>/dev/null || true
    fi
fi

log "Log: $LOG_FILE"
log "=== Runner script done ==="
