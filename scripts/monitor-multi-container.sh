#!/usr/bin/env bash
# Multi-Container Log Monitor
# Monitors backend + sandbox logs with session correlation

set -euo pipefail

BACKEND_CONTAINER="pythinker-backend-1"
SANDBOX_CONTAINER="pythinker-sandbox-1"
SESSION_ID="${1:-}"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Pythinker Multi-Container Log Monitor${NC}"
echo -e "${CYAN}Backend + Sandbox Unified Monitoring${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Check containers
check_container() {
    local container=$1
    if ! docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -e "${RED}Warning: Container ${container} is not running${NC}"
        return 1
    fi
    return 0
}

check_container "${BACKEND_CONTAINER}" || true
check_container "${SANDBOX_CONTAINER}" || true

function show_menu() {
    echo -e "${GREEN}Select monitoring mode:${NC}"
    echo "1) Live Stream - Both Containers (unified)"
    echo "2) Live Stream - Backend Only"
    echo "3) Live Stream - Sandbox Only"
    echo "4) Live Stream - Session Specific (requires SESSION_ID)"
    echo "5) Side-by-Side View (split terminal)"
    echo "6) Recent Errors - Both Containers"
    echo "7) Container Health & Status"
    echo "8) Sandbox Tool Execution Logs"
    echo "9) Backend API Request Logs"
    echo "10) Docker/Browser Logs from Sandbox"
    echo "11) VNC/CDP Connection Logs"
    echo "12) Complete System Snapshot"
    echo "0) Exit"
    echo ""
}

function stream_unified() {
    echo -e "${CYAN}Streaming logs from BOTH containers (Ctrl+C to stop)...${NC}"
    echo -e "${YELLOW}Backend logs: CYAN | Sandbox logs: MAGENTA${NC}"
    echo ""

    # Use docker compose logs if available, otherwise manual merge
    if command -v docker-compose &> /dev/null; then
        cd /Users/panda/Desktop/Projects/Pythinker
        docker-compose logs -f --tail=50 backend sandbox
    else
        # Manual merge with color coding
        (docker logs ${BACKEND_CONTAINER} -f --tail 50 --timestamps 2>&1 | sed "s/^/$(echo -e ${CYAN})[BACKEND]$(echo -e ${NC}) /" ) &
        (docker logs ${SANDBOX_CONTAINER} -f --tail 50 --timestamps 2>&1 | sed "s/^/$(echo -e ${MAGENTA})[SANDBOX]$(echo -e ${NC}) /" ) &
        wait
    fi
}

function stream_backend_only() {
    echo -e "${CYAN}Streaming BACKEND logs only (Ctrl+C to stop)...${NC}"
    docker logs ${BACKEND_CONTAINER} -f --tail 100 --timestamps
}

function stream_sandbox_only() {
    echo -e "${MAGENTA}Streaming SANDBOX logs only (Ctrl+C to stop)...${NC}"
    docker logs ${SANDBOX_CONTAINER} -f --tail 100 --timestamps
}

function stream_session_logs() {
    if [ -z "${SESSION_ID}" ]; then
        read -p "Enter session ID: " SESSION_ID
    fi

    echo -e "${BLUE}Streaming logs for session: ${SESSION_ID}${NC}"
    echo -e "${CYAN}Backend logs:${NC}"
    echo ""

    # Backend session logs
    (docker logs ${BACKEND_CONTAINER} -f --tail 100 --timestamps 2>&1 | \
        grep -E --line-buffered --color=always "session_id=${SESSION_ID}" | \
        sed "s/^/$(echo -e ${CYAN})[BACKEND]$(echo -e ${NC}) /") &

    # Sandbox session logs (if session ID appears)
    (docker logs ${SANDBOX_CONTAINER} -f --tail 100 --timestamps 2>&1 | \
        grep -E --line-buffered --color=always "${SESSION_ID}" | \
        sed "s/^/$(echo -e ${MAGENTA})[SANDBOX]$(echo -e ${NC}) /") &

    wait
}

function stream_side_by_side() {
    echo -e "${YELLOW}Opening side-by-side view...${NC}"
    echo "Left: Backend | Right: Sandbox"
    echo ""

    if command -v tmux &> /dev/null; then
        tmux new-session -d -s pythinker-monitor
        tmux split-window -h
        tmux send-keys -t 0 "docker logs ${BACKEND_CONTAINER} -f --tail 50 --timestamps" C-m
        tmux send-keys -t 1 "docker logs ${SANDBOX_CONTAINER} -f --tail 50 --timestamps" C-m
        tmux attach-session -t pythinker-monitor
    else
        echo -e "${RED}tmux not installed. Install with: brew install tmux${NC}"
        echo "Falling back to unified stream..."
        stream_unified
    fi
}

function show_recent_errors() {
    echo -e "${RED}Recent Errors from BOTH containers (last 5 minutes):${NC}"
    echo ""

    echo -e "${CYAN}=== BACKEND ERRORS ===${NC}"
    docker logs ${BACKEND_CONTAINER} --since 5m --timestamps 2>&1 | \
        grep -E "ERROR|WARNING|CRITICAL|Exception|Traceback" | \
        tail -20 || echo "No errors found"

    echo ""
    echo -e "${MAGENTA}=== SANDBOX ERRORS ===${NC}"
    docker logs ${SANDBOX_CONTAINER} --since 5m --timestamps 2>&1 | \
        grep -E "ERROR|WARNING|CRITICAL|Exception|error|Error" | \
        tail -20 || echo "No errors found"
}

function show_container_health() {
    echo -e "${GREEN}Container Health & Status:${NC}"
    echo ""

    docker ps --filter "name=pythinker" --format "table {{.Names}}\t{{.Status}}\t{{.Health}}\t{{.Ports}}"

    echo ""
    echo -e "${BLUE}Resource Usage:${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
        ${BACKEND_CONTAINER} ${SANDBOX_CONTAINER}
}

function show_sandbox_tool_execution() {
    echo -e "${MAGENTA}Sandbox Tool Execution Logs:${NC}"
    echo ""

    echo "=== Shell Tool Executions ==="
    docker logs ${SANDBOX_CONTAINER} --tail 200 | \
        grep -E "shell|bash|command|execute" | \
        tail -15 || echo "No shell executions found"

    echo ""
    echo "=== File Operations ==="
    docker logs ${SANDBOX_CONTAINER} --tail 200 | \
        grep -E "file|read|write|create|delete" | \
        tail -15 || echo "No file operations found"

    echo ""
    echo "=== Browser Operations ==="
    docker logs ${SANDBOX_CONTAINER} --tail 200 | \
        grep -E "browser|chromium|playwright|CDP" | \
        tail -15 || echo "No browser operations found"
}

function show_backend_api_logs() {
    echo -e "${CYAN}Backend API Request Logs:${NC}"
    echo ""

    echo "=== Recent API Requests ==="
    docker logs ${BACKEND_CONTAINER} --tail 200 | \
        grep -E "POST|GET|PUT|DELETE|/api/v1/" | \
        tail -20 || echo "No API requests found"

    echo ""
    echo "=== Session Events ==="
    docker logs ${BACKEND_CONTAINER} --tail 200 | \
        grep -E "session|SSE|event|stream" | \
        tail -15 || echo "No session events found"
}

function show_docker_browser_logs() {
    echo -e "${MAGENTA}Docker/Browser Logs from Sandbox:${NC}"
    echo ""

    echo "=== Docker Container Management ==="
    docker logs ${SANDBOX_CONTAINER} --tail 200 | \
        grep -E "docker|container|image|volume" | \
        tail -15 || echo "No docker operations found"

    echo ""
    echo "=== Browser/Chromium Logs ==="
    docker logs ${SANDBOX_CONTAINER} --tail 200 | \
        grep -E "chromium|chrome|browser|playwright|page" | \
        tail -15 || echo "No browser logs found"

    echo ""
    echo "=== CDP (Chrome DevTools Protocol) ==="
    docker logs ${SANDBOX_CONTAINER} --tail 200 | \
        grep -E "CDP|DevTools|ws://.*:9222" | \
        tail -10 || echo "No CDP logs found"
}

function show_vnc_cdp_logs() {
    echo -e "${BLUE}VNC/CDP Connection Logs:${NC}"
    echo ""

    echo "=== VNC Server Logs (Sandbox) ==="
    docker logs ${SANDBOX_CONTAINER} --tail 200 | \
        grep -E "VNC|vnc|x11vnc|websockify|5901" | \
        tail -15 || echo "No VNC logs found"

    echo ""
    echo "=== VNC Client Logs (Backend) ==="
    docker logs ${BACKEND_CONTAINER} --tail 200 | \
        grep -E "VNC|vnc|WebSocket.*5901|Connecting to VNC" | \
        tail -15 || echo "No VNC client logs found"

    echo ""
    echo "=== CDP Connection (Backend) ==="
    docker logs ${BACKEND_CONTAINER} --tail 200 | \
        grep -E "CDP|9222|DevTools|playwright.*connect" | \
        tail -15 || echo "No CDP logs found"
}

function show_complete_snapshot() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Complete System Snapshot${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""

    show_container_health
    echo ""

    echo -e "${CYAN}=== Recent Backend Activity (last 30 lines) ===${NC}"
    docker logs ${BACKEND_CONTAINER} --tail 30 --timestamps
    echo ""

    echo -e "${MAGENTA}=== Recent Sandbox Activity (last 30 lines) ===${NC}"
    docker logs ${SANDBOX_CONTAINER} --tail 30 --timestamps
    echo ""

    show_recent_errors
    echo ""

    echo -e "${BLUE}=== Active Sessions ===${NC}"
    docker logs ${BACKEND_CONTAINER} --tail 200 | \
        grep -oP 'session_id=\K[a-f0-9]+' | \
        sort -u | \
        tail -10
    echo ""

    echo -e "${GREEN}========================================${NC}"
}

# Main menu loop
while true; do
    show_menu
    read -p "Enter choice [0-12]: " choice

    case $choice in
        1) stream_unified ;;
        2) stream_backend_only ;;
        3) stream_sandbox_only ;;
        4) stream_session_logs ;;
        5) stream_side_by_side ;;
        6) show_recent_errors ;;
        7) show_container_health ;;
        8) show_sandbox_tool_execution ;;
        9) show_backend_api_logs ;;
        10) show_docker_browser_logs ;;
        11) show_vnc_cdp_logs ;;
        12) show_complete_snapshot ;;
        0) echo "Exiting..."; exit 0 ;;
        *) echo -e "${RED}Invalid option${NC}" ;;
    esac

    echo ""
    read -p "Press Enter to continue..."
    clear
done
