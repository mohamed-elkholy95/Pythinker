#!/bin/bash
set -Eeuo pipefail

# Backend uptime watchdog for local Docker development.
# Recovers backend when container is stopped, missing, unhealthy, or API health
# endpoint fails repeatedly.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_ROOT}/docker-compose.yml}"
SERVICE_NAME="${SERVICE_NAME:-backend}"
CONTAINER_NAME="${CONTAINER_NAME:-}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://localhost:8000/api/v1/health}"
CHECK_INTERVAL="${CHECK_INTERVAL:-15}"
MAX_CONSECUTIVE_FAILURES="${MAX_CONSECUTIVE_FAILURES:-3}"
RECOVERY_COOLDOWN_SECONDS="${RECOVERY_COOLDOWN_SECONDS:-60}"
STARTUP_GRACE_SECONDS="${STARTUP_GRACE_SECONDS:-30}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-5}"
ONCE_MODE=0

FAILURE_COUNT=0
LAST_RECOVERY_EPOCH=0
STARTED_EPOCH="$(date +%s)"
COMPOSE_CMD=()

resolve_container_name() {
    local logical_service="$1"
    local names
    names="$(docker ps -a --format '{{.Names}}')"

    local candidate_main="pythinker-main-${logical_service}-1"
    local candidate_legacy="pythinker-${logical_service}-1"

    if echo "${names}" | grep -Fxq "${candidate_main}"; then
        echo "${candidate_main}"
        return 0
    fi
    if echo "${names}" | grep -Fxq "${candidate_legacy}"; then
        echo "${candidate_legacy}"
        return 0
    fi

    local fallback
    fallback="$(echo "${names}" | grep -E "(^|-)${logical_service}-1$" | head -n 1)"
    if [ -n "${fallback}" ]; then
        echo "${fallback}"
        return 0
    fi
    return 1
}

usage() {
    cat <<EOF
Usage: scripts/backend_watchdog.sh [options]

Options:
  --interval <sec>          Check interval in seconds (default: ${CHECK_INTERVAL})
  --max-failures <count>    Consecutive failures before recovery (default: ${MAX_CONSECUTIVE_FAILURES})
  --cooldown <sec>          Min seconds between recoveries (default: ${RECOVERY_COOLDOWN_SECONDS})
  --startup-grace <sec>     Grace period after start (default: ${STARTUP_GRACE_SECONDS})
  --timeout <sec>           HTTP timeout per health request (default: ${REQUEST_TIMEOUT_SECONDS})
  --container <name>        Backend container name (default: ${CONTAINER_NAME})
  --service <name>          Compose service name (default: ${SERVICE_NAME})
  --compose-file <path>     Compose file path (default: ${COMPOSE_FILE})
  --health-url <url>        Backend health URL (default: ${HEALTHCHECK_URL})
  --once                    Run a single check cycle and exit
  -h, --help                Show help

Environment variables with same names are also supported.
EOF
}

log() {
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "${ts} [backend-watchdog] $*"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --interval|--max-failures|--cooldown|--startup-grace|--timeout|--container|--service|--compose-file|--health-url)
                if [[ $# -lt 2 ]]; then
                    echo "Missing value for option: $1" >&2
                    usage
                    exit 1
                fi
                ;;
        esac

        case "$1" in
            --interval)
                CHECK_INTERVAL="$2"
                shift 2
                ;;
            --max-failures)
                MAX_CONSECUTIVE_FAILURES="$2"
                shift 2
                ;;
            --cooldown)
                RECOVERY_COOLDOWN_SECONDS="$2"
                shift 2
                ;;
            --startup-grace)
                STARTUP_GRACE_SECONDS="$2"
                shift 2
                ;;
            --timeout)
                REQUEST_TIMEOUT_SECONDS="$2"
                shift 2
                ;;
            --container)
                CONTAINER_NAME="$2"
                shift 2
                ;;
            --service)
                SERVICE_NAME="$2"
                shift 2
                ;;
            --compose-file)
                COMPOSE_FILE="$2"
                shift 2
                ;;
            --health-url)
                HEALTHCHECK_URL="$2"
                shift 2
                ;;
            --once)
                ONCE_MODE=1
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1" >&2
                usage
                exit 1
                ;;
        esac
    done
}

is_positive_int() {
    [[ "$1" =~ ^[0-9]+$ ]] && [[ "$1" -ge 1 ]]
}

validate_config() {
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        echo "Compose file not found: $COMPOSE_FILE" >&2
        exit 1
    fi

    for value_name in CHECK_INTERVAL MAX_CONSECUTIVE_FAILURES RECOVERY_COOLDOWN_SECONDS STARTUP_GRACE_SECONDS REQUEST_TIMEOUT_SECONDS; do
        value="${!value_name}"
        if ! is_positive_int "$value"; then
            echo "Invalid ${value_name}: ${value} (must be a positive integer)" >&2
            exit 1
        fi
    done

    if [[ -z "${CONTAINER_NAME}" ]]; then
        CONTAINER_NAME="$(resolve_container_name "${SERVICE_NAME}" || true)"
    fi
}

init_compose_cmd() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD=(docker compose)
        return
    fi

    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD=(docker-compose)
        return
    fi

    echo "Neither 'docker compose' nor 'docker-compose' is available" >&2
    exit 1
}

ensure_docker_ready() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "'docker' command not found" >&2
        exit 1
    fi

    if ! docker info >/dev/null 2>&1; then
        echo "Docker daemon is not reachable" >&2
        exit 1
    fi
}

container_exists() {
    docker inspect "$CONTAINER_NAME" >/dev/null 2>&1
}

container_running() {
    [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || echo false)" == "true" ]]
}

container_health_status() {
    docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown"
}

backend_health_ok() {
    curl -fsS --max-time "$REQUEST_TIMEOUT_SECONDS" "$HEALTHCHECK_URL" >/dev/null 2>&1
}

compose_recreate_backend() {
    if "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" up -d --no-deps --no-build "$SERVICE_NAME" >/dev/null 2>&1; then
        return 0
    fi

    # Compatibility fallback for older compose variants that may reject --no-build.
    "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE" up -d --no-deps "$SERVICE_NAME" >/dev/null 2>&1
}

recover_backend() {
    local now
    now="$(date +%s)"

    if (( now - LAST_RECOVERY_EPOCH < RECOVERY_COOLDOWN_SECONDS )); then
        log "Recovery throttled by cooldown (${RECOVERY_COOLDOWN_SECONDS}s)"
        return 1
    fi
    LAST_RECOVERY_EPOCH="$now"

    if container_exists; then
        if container_running; then
            log "Restarting running container '${CONTAINER_NAME}'"
            if ! docker restart -t 15 "$CONTAINER_NAME" >/dev/null 2>&1; then
                log "Container restart failed, falling back to compose recovery"
                if ! compose_recreate_backend; then
                    log "Recovery failed: compose fallback failed"
                    return 1
                fi
            fi
        else
            log "Starting stopped container '${CONTAINER_NAME}'"
            if ! docker start "$CONTAINER_NAME" >/dev/null 2>&1; then
                log "Container start failed, falling back to compose recovery"
                if ! compose_recreate_backend; then
                    log "Recovery failed: compose fallback failed"
                    return 1
                fi
            fi
        fi
    else
        log "Container '${CONTAINER_NAME}' does not exist, creating with compose"
        if ! compose_recreate_backend; then
            log "Recovery failed: could not create backend container"
            return 1
        fi
    fi

    FAILURE_COUNT=0
    return 0
}

run_single_check() {
    local health_status
    local api_ok=1
    local in_grace=0
    local now
    local reason="healthy"

    now="$(date +%s)"
    if (( now - STARTED_EPOCH < STARTUP_GRACE_SECONDS )); then
        in_grace=1
    fi

    if ! container_exists; then
        reason="container_missing"
    elif ! container_running; then
        reason="container_stopped"
    else
        health_status="$(container_health_status)"
        if [[ "$health_status" == "unhealthy" ]]; then
            reason="container_unhealthy"
        fi

        if ! backend_health_ok; then
            api_ok=0
            if [[ "$reason" == "healthy" ]]; then
                reason="health_endpoint_failed"
            else
                reason="${reason}+health_endpoint_failed"
            fi
        fi
    fi

    if [[ "$reason" == "healthy" ]]; then
        if (( FAILURE_COUNT > 0 )); then
            log "Health recovered after ${FAILURE_COUNT} consecutive failure(s)"
        fi
        FAILURE_COUNT=0
        return 0
    fi

    if (( in_grace == 1 )); then
        log "Detected '${reason}' during startup grace (${STARTUP_GRACE_SECONDS}s), skipping recovery"
        return 1
    fi

    FAILURE_COUNT=$((FAILURE_COUNT + 1))
    log "Detected '${reason}' (consecutive failures: ${FAILURE_COUNT}/${MAX_CONSECUTIVE_FAILURES})"

    if (( FAILURE_COUNT >= MAX_CONSECUTIVE_FAILURES )); then
        log "Failure threshold reached, attempting recovery"
        if recover_backend; then
            log "Recovery completed"
        else
            log "Recovery attempt failed"
        fi
    fi

    if (( api_ok == 0 )); then
        return 1
    fi
    return 1
}

main() {
    parse_args "$@"
    validate_config
    ensure_docker_ready
    init_compose_cmd

    trap 'log "Received stop signal, exiting"; exit 0' INT TERM

    log "Started with container=${CONTAINER_NAME} service=${SERVICE_NAME} compose_file=${COMPOSE_FILE}"
    log "Settings: interval=${CHECK_INTERVAL}s max_failures=${MAX_CONSECUTIVE_FAILURES} cooldown=${RECOVERY_COOLDOWN_SECONDS}s startup_grace=${STARTUP_GRACE_SECONDS}s"

    if (( ONCE_MODE == 1 )); then
        if run_single_check; then
            exit 0
        fi
        exit 1
    fi

    while true; do
        run_single_check || true
        sleep "$CHECK_INTERVAL"
    done
}

main "$@"
