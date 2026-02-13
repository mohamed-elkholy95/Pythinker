#!/bin/bash
# Auto-Retry and Status Reconciliation Test Helper
# This script helps monitor and verify the auto-retry implementation

set -e

BACKEND_CONTAINER="pythinker-backend-1"
FRONTEND_URL="http://localhost:5174"
BACKEND_URL="http://localhost:8000"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Pythinker Auto-Retry & Status Reconciliation Test${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"

# Function to print section headers
print_section() {
    echo -e "\n${YELLOW}▶ $1${NC}"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print info
print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if containers are running
print_section "Checking Environment"

if docker ps | grep -q "$BACKEND_CONTAINER"; then
    print_success "Backend container is running"
else
    print_error "Backend container is not running"
    echo "Run: ./dev.sh up -d"
    exit 1
fi

# Check if frontend is accessible
if curl -s "$FRONTEND_URL" > /dev/null; then
    print_success "Frontend is accessible at $FRONTEND_URL"
else
    print_error "Frontend is not accessible at $FRONTEND_URL"
    exit 1
fi

# Function to watch backend logs for specific patterns
watch_backend_logs() {
    print_section "Watching Backend Logs (Ctrl+C to stop)"
    print_info "Looking for: timeout, reconnect, heartbeat, SSE, status"
    docker logs -f "$BACKEND_CONTAINER" 2>&1 | grep -E --color=always "(timeout|reconnect|heartbeat|SSE|status|Session.*running|Session.*completed|DoneEvent)" || true
}

# Function to check session status
check_session_status() {
    local session_id="$1"
    if [ -z "$session_id" ]; then
        echo "Usage: check_session_status <session_id>"
        return 1
    fi

    print_section "Checking Session Status: $session_id"

    # Note: This requires authentication token
    # curl -s "$BACKEND_URL/sessions/$session_id/status" \
    #     -H "Authorization: Bearer YOUR_TOKEN"

    print_info "Check session status in browser Console:"
    echo "  sessionStatus.value"
    echo "  responsePhase.value"
}

# Function to display test instructions
show_test_menu() {
    echo -e "\n${YELLOW}Available Tests:${NC}"
    echo "  1) Test Auto-Retry (Progressive Backoff)"
    echo "  2) Test Status Reconciliation"
    echo "  3) Test Manual Retry Cancels Auto-Retry"
    echo "  4) Test Session Persistence on Navigation"
    echo "  5) Watch Backend Logs (Real-time)"
    echo "  6) Check Recent Backend Logs"
    echo "  7) Show Browser Console Commands"
    echo "  8) Exit"
    echo ""
}

# Function to show browser console commands
show_browser_commands() {
    print_section "Browser Console Commands"
    echo ""
    echo "Check current state:"
    echo "  responsePhase.value          // Current response phase"
    echo "  autoRetryCount.value         // Auto-retry attempt count"
    echo "  lastError.value              // Last error details"
    echo "  sessionStatus.value          // Session status"
    echo "  sessionId.value              // Current session ID"
    echo ""
    echo "Enable verbose logging:"
    echo "  localStorage.setItem('debug', 'pythinker:*')"
    echo ""
    echo "Force state transitions (DEV ONLY):"
    echo "  transitionTo('timed_out')    // Simulate timeout"
    echo "  transitionTo('error')        // Simulate error"
    echo ""
}

# Function to show test 1 instructions
test_auto_retry() {
    print_section "Test 1: Auto-Retry with Progressive Backoff"
    echo ""
    echo "Steps:"
    echo "  1. Open $FRONTEND_URL in browser"
    echo "  2. Open DevTools (F12) → Console and Network tabs"
    echo "  3. Start a simple task (e.g., 'What is 2+2?')"
    echo "  4. In Network tab, select 'Offline' from throttling dropdown"
    echo "  5. Wait for SSE timeout (~5-10 seconds)"
    echo ""
    echo "Expected Console Logs:"
    echo "  [AutoRetry] Scheduling retry 1/3 in 5s"
    echo "  [ResponsePhase] timed_out → connecting"
    echo "  [AutoRetry] Scheduling retry 2/3 in 15s"
    echo "  [AutoRetry] Scheduling retry 3/3 in 45s"
    echo ""
    echo "Expected UI:"
    echo "  • Timeout notice: 'Connection interrupted. Reconnecting automatically...'"
    echo "  • After 3 failed retries: 'Connection interrupted. The agent may still be working.'"
    echo "  • 'Retry' button always visible"
    echo ""
    echo "Re-enable network and verify auto-retry succeeds"
    echo ""
}

# Function to show test 2 instructions
test_status_reconciliation() {
    print_section "Test 2: Status Reconciliation"
    echo ""
    echo "Steps:"
    echo "  1. Start a long-running task (e.g., 'Search web and summarize AI news')"
    echo "  2. Go offline in DevTools Network tab"
    echo "  3. Wait for SSE timeout"
    echo "  4. Check backend logs: docker logs $BACKEND_CONTAINER --tail 50"
    echo "  5. Look for 'DoneEvent' or 'Chat completed' in logs"
    echo "  6. Re-enable network and click 'Retry'"
    echo ""
    echo "Expected Behavior:"
    echo "  • Status check happens BEFORE SSE reconnect"
    echo "  • Instant transition to 'completing' → 'settled'"
    echo "  • NO 'connecting' flash"
    echo "  • Suggestions appear immediately"
    echo ""
    echo "Console Logs to Check:"
    echo "  [ResponsePhase] timed_out → connecting"
    echo "  [ResponsePhase] connecting → completing"
    echo "  [ResponsePhase] completing → settled"
    echo ""
}

# Function to show test 3 instructions
test_manual_retry() {
    print_section "Test 3: Manual Retry Cancels Auto-Retry"
    echo ""
    echo "Steps:"
    echo "  1. Trigger timeout (go offline)"
    echo "  2. Wait for auto-retry countdown to start"
    echo "  3. BEFORE timer fires, click 'Retry' button manually"
    echo ""
    echo "Expected:"
    echo "  • Auto-retry timer cancelled"
    echo "  • Manual retry starts immediately"
    echo "  • Only ONE retry attempt (not two)"
    echo ""
    echo "Check in Console:"
    echo "  autoRetryTimer.value  // Should be null after manual retry"
    echo ""
}

# Function to show test 4 instructions
test_session_persistence() {
    print_section "Test 4: Session Persistence on Navigation"
    echo ""
    echo "Steps:"
    echo "  1. Start a long task in Session A"
    echo "  2. Click 'New Chat' (creates Session B)"
    echo "  3. Verify Session A continues in background"
    echo "  4. Return to Session A and verify it resumes"
    echo ""
    echo "Backend logs to check:"
    print_info "Run in separate terminal:"
    echo "  docker logs -f $BACKEND_CONTAINER | grep -E '(Session|stopping|task)'"
    echo ""
    echo "Should NOT see:"
    echo "  'stopping session' when navigating between RUNNING sessions"
    echo ""
    echo "Should see:"
    echo "  Session continues generating events"
    echo ""
}

# Function to check recent backend logs
check_recent_logs() {
    print_section "Recent Backend Logs (Last 100 lines)"
    docker logs --tail 100 "$BACKEND_CONTAINER" 2>&1 | grep -E --color=always "(timeout|reconnect|heartbeat|SSE|ERROR|Session.*completed|DoneEvent)" || print_info "No matching logs found"
}

# Main menu loop
main() {
    while true; do
        show_test_menu
        read -p "Select test (1-8): " choice

        case $choice in
            1)
                test_auto_retry
                ;;
            2)
                test_status_reconciliation
                ;;
            3)
                test_manual_retry
                ;;
            4)
                test_session_persistence
                ;;
            5)
                watch_backend_logs
                ;;
            6)
                check_recent_logs
                ;;
            7)
                show_browser_commands
                ;;
            8)
                echo -e "\n${GREEN}Exiting...${NC}"
                exit 0
                ;;
            *)
                print_error "Invalid choice. Please select 1-8."
                ;;
        esac

        echo ""
        read -p "Press Enter to continue..."
    done
}

# Run main menu
main
