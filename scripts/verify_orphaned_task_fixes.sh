#!/bin/bash
#
# Orphaned Task Fix Verification Script
#
# Verifies that all fixes for the orphaned background task issue are correctly implemented.
#
# Usage: ./scripts/verify_orphaned_task_fixes.sh

set -e

echo "======================================"
echo "Orphaned Task Fix Verification"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0

# Helper functions
pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

section() {
    echo ""
    echo "======================================"
    echo "$1"
    echo "======================================"
}

# ====================
# 1. Code Changes Verification
# ====================

section "1. Verifying Code Changes"

# Check Fix 1: Pre-emission cancellation check (parallel path)
if grep -q "ORPHANED TASK FIX: Check cancellation BEFORE emitting tool event" backend/app/domain/services/agents/base.py; then
    if grep -A 3 "ORPHANED TASK FIX: Check cancellation BEFORE emitting tool event" backend/app/domain/services/agents/base.py | grep -q "await self._cancel_token.check_cancelled()"; then
        pass "Fix 1a: Pre-emission check (parallel path) - PRESENT"
    else
        fail "Fix 1a: Pre-emission check code missing"
    fi
else
    fail "Fix 1a: Pre-emission check comment missing"
fi

# Check Fix 1b: Pre-emission cancellation check (sequential path)
COUNT=$(grep -c "ORPHANED TASK FIX: Check cancellation BEFORE emitting tool event" backend/app/domain/services/agents/base.py || true)
if [ "$COUNT" -ge 2 ]; then
    pass "Fix 1b: Pre-emission check (sequential path) - PRESENT"
else
    fail "Fix 1b: Pre-emission check (sequential path) - MISSING (found $COUNT occurrences, expected 2)"
fi

# Check Fix 2: Pre-invocation cancellation check
if grep -q "ORPHANED TASK FIX: Check cancellation BEFORE invoking" backend/app/domain/services/agents/base.py; then
    pass "Fix 2: Pre-invocation check - PRESENT"
else
    fail "Fix 2: Pre-invocation check - MISSING"
fi

# Check Fix 3: Immediate cancellation on client disconnect
if grep -q 'close_reason == "client_disconnected"' backend/app/interfaces/api/session_routes.py; then
    if grep -A 4 'close_reason == "client_disconnected"' backend/app/interfaces/api/session_routes.py | grep -q "request_cancellation(session_id)"; then
        pass "Fix 3: Immediate cancellation - PRESENT"
    else
        fail "Fix 3: Immediate cancellation logic missing"
    fi
else
    fail "Fix 3: client_disconnected check missing"
fi

# Check Fix 3b: Reduced grace period for generator_cancelled
if grep -q "grace_seconds=5.0" backend/app/interfaces/api/session_routes.py; then
    pass "Fix 3b: Reduced grace period (5s) - PRESENT"
else
    fail "Fix 3b: Grace period not reduced (should be 5.0, not 45.0)"
fi

# Check Fix 4: Background task cleanup
if grep -q "ORPHANED TASK FIX: Cancel all background tasks" backend/app/domain/services/agent_task_runner.py; then
    if grep -A 10 "ORPHANED TASK FIX: Cancel all background tasks" backend/app/domain/services/agent_task_runner.py | grep -q "task.cancel()"; then
        pass "Fix 4: Background task cleanup - PRESENT"
    else
        fail "Fix 4: Background task cleanup code missing"
    fi
else
    fail "Fix 4: Background task cleanup - MISSING"
fi

# ====================
# 2. Cleanup Service Verification
# ====================

section "2. Verifying Cleanup Service"

# Check cleanup service exists
if [ -f "backend/app/application/services/orphaned_task_cleanup_service.py" ]; then
    pass "Cleanup service file exists"

    # Check for main class
    if grep -q "class OrphanedTaskCleanupService:" backend/app/application/services/orphaned_task_cleanup_service.py; then
        pass "OrphanedTaskCleanupService class defined"
    else
        fail "OrphanedTaskCleanupService class not found"
    fi

    # Check for cleanup methods
    if grep -q "async def run_cleanup(" backend/app/application/services/orphaned_task_cleanup_service.py; then
        pass "run_cleanup() method defined"
    else
        fail "run_cleanup() method not found"
    fi

else
    fail "Cleanup service file missing"
fi

# Check scheduler integration
if [ -f "backend/app/application/services/cleanup_scheduler.py" ]; then
    pass "Cleanup scheduler file exists"
else
    fail "Cleanup scheduler file missing"
fi

# ====================
# 3. Metrics Verification
# ====================

section "3. Verifying Prometheus Metrics"

# Check metrics added
if grep -q "orphaned_task_cleanup_runs_total" backend/app/infrastructure/observability/prometheus_metrics.py; then
    pass "Cleanup metrics defined"

    # Check all 4 metrics
    METRICS=(
        "orphaned_task_cleanup_runs_total"
        "orphaned_redis_streams_cleaned_total"
        "zombie_sessions_cleaned_total"
        "orphaned_task_cleanup_duration_seconds"
    )

    for metric in "${METRICS[@]}"; do
        if grep -q "$metric" backend/app/infrastructure/observability/prometheus_metrics.py; then
            pass "  - $metric: PRESENT"
        else
            fail "  - $metric: MISSING"
        fi
    done

    # Check helper function
    if grep -q "def record_orphaned_task_cleanup(" backend/app/infrastructure/observability/prometheus_metrics.py; then
        pass "record_orphaned_task_cleanup() function defined"
    else
        fail "record_orphaned_task_cleanup() function missing"
    fi

    # Check metrics registered
    if grep -q "orphaned_task_cleanup_runs_total," backend/app/infrastructure/observability/prometheus_metrics.py; then
        pass "Metrics registered in _metrics_registry"
    else
        warn "Metrics may not be registered (check manually)"
    fi

else
    fail "Cleanup metrics not found"
fi

# ====================
# 4. Test Suite Verification
# ====================

section "4. Verifying Test Suite"

if [ -f "backend/tests/domain/services/test_orphaned_task_prevention.py" ]; then
    pass "Test file exists"

    # Count test methods
    TEST_COUNT=$(grep -c "def test_" backend/tests/domain/services/test_orphaned_task_prevention.py || true)
    if [ "$TEST_COUNT" -ge 10 ]; then
        pass "Test suite has $TEST_COUNT tests (expected >=10)"
    else
        warn "Test suite only has $TEST_COUNT tests (expected >=10)"
    fi

    # Check key tests exist
    KEY_TESTS=(
        "test_tool_not_emitted_when_cancelled"
        "test_tool_not_invoked_when_cancelled"
        "test_immediate_cancellation_on_client_disconnect"
        "test_background_tasks_cancelled_on_destroy"
        "test_race_condition_prevention"
    )

    for test in "${KEY_TESTS[@]}"; do
        if grep -q "$test" backend/tests/domain/services/test_orphaned_task_prevention.py; then
            pass "  - $test: PRESENT"
        else
            fail "  - $test: MISSING"
        fi
    done

else
    fail "Test file missing"
fi

# ====================
# 5. Documentation Verification
# ====================

section "5. Verifying Documentation"

DOCS=(
    "docs/operations/ORPHANED_TASK_CLEANUP.md"
    "ORPHANED_TASKS_FIX_SUMMARY.md"
    "ISSUES_DEEP_DIVE.md"
)

for doc in "${DOCS[@]}"; do
    if [ -f "$doc" ]; then
        pass "Documentation: $doc"
    else
        fail "Documentation missing: $doc"
    fi
done

# ====================
# 6. Runtime Verification (if containers running)
# ====================

section "6. Runtime Verification (optional)"

if docker ps | grep -q "pythinker-backend-1"; then
    pass "Backend container is running"

    echo ""
    echo "Testing cleanup service execution..."

    # Test cleanup service
    if docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service 2>&1 | grep -q "Cleanup completed"; then
        pass "Cleanup service executes successfully"
    else
        warn "Cleanup service execution failed (check logs)"
    fi

    echo ""
    echo "Checking metrics endpoint..."

    # Check metrics endpoint (if accessible)
    if command -v curl &> /dev/null; then
        if curl -s http://localhost:8000/metrics 2>&1 | grep -q "orphaned_task_cleanup"; then
            pass "Cleanup metrics available at /metrics"
        else
            warn "Cleanup metrics not yet available (may need app restart)"
        fi
    else
        warn "curl not available - skipping metrics check"
    fi

else
    warn "Backend container not running - skipping runtime tests"
    echo "     To test manually: docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service"
fi

# ====================
# Summary
# ====================

section "Verification Summary"

TOTAL=$((PASSED + FAILED))
PERCENTAGE=$((PASSED * 100 / TOTAL))

echo ""
echo "Results:"
echo "  Passed: $PASSED"
echo "  Failed: $FAILED"
echo "  Total:  $TOTAL"
echo "  Success Rate: $PERCENTAGE%"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All verifications passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Run tests: cd backend && pytest tests/domain/services/test_orphaned_task_prevention.py"
    echo "  2. Deploy to production"
    echo "  3. Enable cleanup scheduler (see docs/operations/ORPHANED_TASK_CLEANUP.md)"
    echo "  4. Monitor metrics for 1 week"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some verifications failed!${NC}"
    echo ""
    echo "Please review the failures above and fix before deploying."
    echo ""
    exit 1
fi
