#!/usr/bin/env bash
# Session Watchdog Monitoring Script
# Monitors Pythinker agent stuck detection, session health, and task execution

set -euo pipefail

resolve_backend_container() {
    local names
    names="$(docker ps -a --format '{{.Names}}')"

    if echo "${names}" | grep -Fxq "pythinker-main-backend-1"; then
        echo "pythinker-main-backend-1"
        return 0
    fi
    if echo "${names}" | grep -Fxq "pythinker-backend-1"; then
        echo "pythinker-backend-1"
        return 0
    fi

    local fallback
    fallback="$(echo "${names}" | grep -E '(^|-)backend-1$' | head -n 1)"
    if [ -n "${fallback}" ]; then
        echo "${fallback}"
        return 0
    fi

    return 1
}

CONTAINER_NAME="${CONTAINER_NAME:-$(resolve_backend_container || true)}"
SESSION_ID="${1:-}"  # Optional: pass session ID as first arg

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Pythinker Session Watchdog Monitor${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if container is running
if [ -z "${CONTAINER_NAME}" ]; then
    echo -e "${RED}Error: Could not resolve backend container name${NC}"
    exit 1
fi
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: Container ${CONTAINER_NAME} is not running${NC}"
    exit 1
fi

function show_menu() {
    echo -e "${GREEN}Select monitoring mode:${NC}"
    echo "1) Live Stream - All Logs"
    echo "2) Live Stream - Stuck Detection Only"
    echo "3) Live Stream - Session Specific (requires SESSION_ID)"
    echo "4) Recent Errors & Warnings (last 5 min)"
    echo "5) Stuck Detection Statistics"
    echo "6) Session Lifecycle Events"
    echo "7) Tool Action Patterns"
    echo "8) Prometheus Metrics (stuck detections)"
    echo "9) Complete Watchdog Report"
    echo "0) Exit"
    echo ""
}

function stream_all_logs() {
    echo -e "${BLUE}Streaming all backend logs (Ctrl+C to stop)...${NC}"
    docker logs ${CONTAINER_NAME} -f --tail 100 --timestamps
}

function stream_stuck_detection() {
    echo -e "${YELLOW}Streaming stuck detection events (Ctrl+C to stop)...${NC}"
    echo -e "${YELLOW}Watching for: stuck patterns, recovery attempts, confidence scores${NC}"
    echo ""
    docker logs ${CONTAINER_NAME} -f --tail 50 --timestamps 2>&1 | \
        grep -E --line-buffered --color=always "stuck|Stuck|STUCK|recovery|confidence|loop_type|StuckAnalysis"
}

function stream_session_logs() {
    if [ -z "${SESSION_ID}" ]; then
        read -p "Enter session ID: " SESSION_ID
    fi
    echo -e "${BLUE}Streaming logs for session: ${SESSION_ID}${NC}"
    docker logs ${CONTAINER_NAME} -f --tail 100 --timestamps 2>&1 | \
        grep -E --line-buffered --color=always "session_id=${SESSION_ID}|SESSION_ID.*${SESSION_ID}"
}

function show_recent_errors() {
    echo -e "${RED}Recent Errors & Warnings (last 5 minutes):${NC}"
    echo ""
    docker logs ${CONTAINER_NAME} --since 5m --timestamps 2>&1 | \
        grep -E "ERROR|WARNING|CRITICAL|Exception|Traceback" | \
        tail -30
}

function show_stuck_stats() {
    echo -e "${YELLOW}Stuck Detection Statistics:${NC}"
    echo ""

    echo "=== Hash-based Stuck Patterns ==="
    docker logs ${CONTAINER_NAME} --tail 500 | \
        grep -i "stuck pattern detected.*hash-based" | \
        tail -10 || echo "No hash-based stuck patterns found"

    echo ""
    echo "=== Semantic Stuck Patterns ==="
    docker logs ${CONTAINER_NAME} --tail 500 | \
        grep -i "stuck pattern detected.*semantic" | \
        tail -10 || echo "No semantic stuck patterns found"

    echo ""
    echo "=== Recovery Attempts ==="
    docker logs ${CONTAINER_NAME} --tail 500 | \
        grep -i "recovery attempt" | \
        tail -10 || echo "No recovery attempts found"

    echo ""
    echo "=== Action-Based Stuck Patterns ==="
    docker logs ${CONTAINER_NAME} --tail 500 | \
        grep -i "action stuck pattern detected" | \
        tail -10 || echo "No action stuck patterns found"
}

function show_session_lifecycle() {
    echo -e "${GREEN}Session Lifecycle Events (last 100):${NC}"
    echo ""
    docker logs ${CONTAINER_NAME} --tail 1000 | \
        grep -E "session_created|session_stopped|agent_started|agent_stopped|Session.*created|Session.*terminated" | \
        tail -20
}

function show_tool_patterns() {
    echo -e "${YELLOW}Tool Action Patterns:${NC}"
    echo ""

    echo "=== Browser Stuck Patterns ==="
    docker logs ${CONTAINER_NAME} --tail 500 | \
        grep -E "BROWSER_SAME_PAGE_LOOP|BROWSER_SCROLL_NO_PROGRESS|BROWSER_CLICK_FAILURES" | \
        tail -10 || echo "No browser stuck patterns"

    echo ""
    echo "=== Excessive Same Tool ==="
    docker logs ${CONTAINER_NAME} --tail 500 | \
        grep -i "EXCESSIVE_SAME_TOOL" | \
        tail -10 || echo "No excessive tool usage"

    echo ""
    echo "=== URL Revisit Patterns ==="
    docker logs ${CONTAINER_NAME} --tail 500 | \
        grep -i "URL_REVISIT_PATTERN" | \
        tail -10 || echo "No URL revisit patterns"

    echo ""
    echo "=== No Progress Detection ==="
    docker logs ${CONTAINER_NAME} --tail 500 | \
        grep -i "NO_PROGRESS" | \
        tail -10 || echo "No progress issues detected"
}

function show_prometheus_metrics() {
    echo -e "${BLUE}Prometheus Metrics (requires Prometheus on :9090):${NC}"
    echo ""

    if command -v curl &> /dev/null; then
        echo "=== Agent Stuck Detections (Total) ==="
        curl -s 'http://localhost:9090/api/v1/query?query=pythinker_agent_stuck_detections_total' | \
            python3 -m json.tool 2>/dev/null || echo "Metric not available or Prometheus not running"

        echo ""
        echo "=== Step Failures ==="
        curl -s 'http://localhost:9090/api/v1/query?query=pythinker_step_failures_total' | \
            python3 -m json.tool 2>/dev/null || echo "Metric not available"

        echo ""
        echo "=== Tool Errors ==="
        curl -s 'http://localhost:9090/api/v1/query?query=pythinker_tool_errors_total' | \
            python3 -m json.tool 2>/dev/null || echo "Metric not available"
    else
        echo "curl not installed - cannot fetch Prometheus metrics"
        echo "Install with: brew install curl"
    fi
}

function show_complete_report() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Complete Watchdog Health Report${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""

    echo -e "${BLUE}1. Container Status${NC}"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"
    echo ""

    echo -e "${BLUE}2. Recent Activity (last minute)${NC}"
    docker logs ${CONTAINER_NAME} --since 1m --timestamps 2>&1 | tail -20
    echo ""

    show_stuck_stats
    echo ""

    echo -e "${BLUE}3. Active Sessions${NC}"
    docker logs ${CONTAINER_NAME} --tail 200 | \
        grep -E "session_id=" | \
        awk -F'session_id=' '{print $2}' | \
        awk '{print $1}' | \
        sort -u | \
        tail -10
    echo ""

    echo -e "${BLUE}4. Error Summary (last hour)${NC}"
    docker logs ${CONTAINER_NAME} --since 1h 2>&1 | \
        grep -E "ERROR|CRITICAL" | \
        wc -l | \
        xargs echo "Total errors:"
    echo ""

    echo -e "${GREEN}========================================${NC}"
}

# Main menu loop
while true; do
    show_menu
    read -p "Enter choice [0-9]: " choice

    case $choice in
        1) stream_all_logs ;;
        2) stream_stuck_detection ;;
        3) stream_session_logs ;;
        4) show_recent_errors ;;
        5) show_stuck_stats ;;
        6) show_session_lifecycle ;;
        7) show_tool_patterns ;;
        8) show_prometheus_metrics ;;
        9) show_complete_report ;;
        0) echo "Exiting..."; exit 0 ;;
        *) echo -e "${RED}Invalid option${NC}" ;;
    esac

    echo ""
    read -p "Press Enter to continue..."
    clear
done
