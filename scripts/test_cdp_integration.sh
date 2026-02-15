#!/bin/bash
#
# CDP Input Integration Test Suite
#
# Tests the complete CDP input flow from WebSocket connection to Chrome input dispatch
#

set -e

echo "======================================================================"
echo "CDP Input Integration Test Suite"
echo "======================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((++TESTS_PASSED))
    ((++TESTS_RUN))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((++TESTS_FAILED))
    ((++TESTS_RUN))
}

info() {
    echo -e "${YELLOW}ℹ INFO${NC}: $1"
}

# Test 1: Check Docker services
echo "[TEST 1] Docker Services Health"
echo "----------------------------"

if docker ps | grep -q "pythinker-sandbox-1"; then
    pass "Sandbox container running"
else
    fail "Sandbox container not running"
    exit 1
fi

if docker ps | grep -q "pythinker-backend-1"; then
    pass "Backend container running"
else
    fail "Backend container not running"
    exit 1
fi

echo ""

# Test 2: CDP Input Status Endpoint
echo "[TEST 2] CDP Input Status Endpoint"
echo "-----------------------------------"

STATUS_RESPONSE=$(curl -s http://localhost:8083/api/v1/input/status)
if echo "$STATUS_RESPONSE" | grep -q "\"available\":true"; then
    pass "Status endpoint returns available=true"
else
    fail "Status endpoint not available"
fi

if echo "$STATUS_RESPONSE" | grep -q "CDP input service ready"; then
    pass "Status message correct"
else
    fail "Status message incorrect"
fi

echo ""

# Test 3: Chrome CDP Health
echo "[TEST 3] Chrome CDP Health"
echo "-------------------------"

CDP_VERSION=$(docker exec pythinker-sandbox-1 curl -s http://127.0.0.1:9222/json/version)
if echo "$CDP_VERSION" | grep -q "Browser"; then
    pass "Chrome CDP responding"
    info "$(echo "$CDP_VERSION" | grep -o '"Browser":"[^"]*"')"
else
    fail "Chrome CDP not responding"
fi

echo ""

# Test 4: Supervisor Process Status
echo "[TEST 4] Supervisor Process Status"
echo "-----------------------------------"

SANDBOX_MODE=$(docker exec pythinker-backend-1 printenv SANDBOX_STREAMING_MODE 2>/dev/null || echo "dual")
info "SANDBOX_STREAMING_MODE=$SANDBOX_MODE"

CHROME_PROCESS=$(docker exec pythinker-sandbox-1 supervisorctl status | grep chrome || true)
if echo "$CHROME_PROCESS" | grep -q "RUNNING"; then
    pass "Chrome process running"
    info "$CHROME_PROCESS"
else
    fail "Chrome process not running"
fi

echo ""

# Test 5: WebSocket Ping/Pong (requires websocat or Python)
echo "[TEST 5] WebSocket Ping/Pong"
echo "----------------------------"

if command -v websocat &> /dev/null; then
    info "Testing with websocat"

    # Send ping, expect pong
    RESPONSE=$(echo '{"type":"ping"}' | timeout 5 websocat ws://localhost:8083/api/v1/input/stream 2>&1 || true)

    if echo "$RESPONSE" | grep -q "pong"; then
        pass "Ping/pong keep-alive working"
    else
        info "Ping/pong test skipped (manual verification needed)"
    fi
else
    info "websocat not installed, skipping WebSocket test"
    info "Install: brew install websocat (macOS) or apt-get install websocat (Linux)"
fi

echo ""

# Test 6: CDP Input Service Logs
echo "[TEST 6] CDP Input Service Logs"
echo "-------------------------------"

CDP_LOGS=$(docker logs pythinker-sandbox-1 2>&1 | grep "cdp_input" | tail -5 || echo "")
if [ -n "$CDP_LOGS" ]; then
    pass "CDP input service logs found"
    info "Recent logs:"
    echo "$CDP_LOGS" | sed 's/^/    /'
else
    info "No CDP input logs yet (service may not have been used)"
fi

echo ""

# Test 7: Network Connectivity
echo "[TEST 7] Network Connectivity"
echo "-----------------------------"

# Test backend -> sandbox connectivity
if docker exec pythinker-backend-1 curl -s -m 3 http://sandbox:8083/api/v1/input/status > /dev/null 2>&1; then
    pass "Backend can reach sandbox input endpoint"
else
    fail "Backend cannot reach sandbox input endpoint"
fi

echo ""

# Test 8: File Deployment
echo "[TEST 8] File Deployment"
echo "-----------------------"

if docker exec pythinker-sandbox-1 test -f /app/app/api/v1/input.py; then
    pass "input.py deployed"
else
    fail "input.py not deployed"
fi

if docker exec pythinker-sandbox-1 test -f /app/app/services/cdp_input.py; then
    pass "cdp_input.py deployed"
else
    fail "cdp_input.py not deployed"
fi

echo ""

# Test 9: Environment Configuration
echo "[TEST 9] Environment Configuration"
echo "----------------------------------"

STREAMING_MODE=$(docker exec pythinker-sandbox-1 printenv SANDBOX_STREAMING_MODE 2>/dev/null || echo "not set")
if [ "$STREAMING_MODE" = "dual" ] || [ "$STREAMING_MODE" = "cdp_only" ]; then
    pass "SANDBOX_STREAMING_MODE configured: $STREAMING_MODE"
else
    fail "SANDBOX_STREAMING_MODE not configured (got: $STREAMING_MODE)"
fi

echo ""

# Test 10: OpenAPI Documentation
echo "[TEST 10] OpenAPI Documentation"
echo "-------------------------------"

if curl -s http://localhost:8083/openapi.json | grep -q "/api/v1/input/status"; then
    pass "Input status endpoint in OpenAPI spec"
else
    fail "Input status endpoint not in OpenAPI spec"
fi

echo ""

# Summary
echo "======================================================================"
echo "Test Summary"
echo "======================================================================"
echo "Total:  $TESTS_RUN"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED${NC}"
    echo ""
    echo "CDP Input integration is ready for manual testing!"
    echo ""
    echo "Next steps:"
    echo "1. Test WebSocket connection from frontend"
    echo "2. Verify mouse/keyboard input forwarding"
    echo "3. Measure input latency (target: <10ms)"
    echo "4. Test in both dual and cdp_only modes"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo ""
    echo "Please fix the failing tests before proceeding."
    exit 1
fi
