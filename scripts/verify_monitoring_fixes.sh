#!/bin/bash
# Verification Script for All Monitoring Fixes
# Run this to verify all implementations are working correctly

set -e  # Exit on error

echo "=========================================="
echo "Monitoring Fixes Verification Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to backend directory
cd "$(dirname "$0")/../backend"

echo "Step 1: Syntax Check"
echo "--------------------"
echo "Checking Python syntax for modified files..."

FILES=(
    "app/core/config.py"
    "app/core/sandbox_pool.py"
    "app/domain/models/pressure.py"
    "app/domain/services/agents/token_manager.py"
    "app/application/services/screenshot_service.py"
    "app/infrastructure/external/browser/playwright_browser.py"
    "app/infrastructure/observability/prometheus_metrics.py"
    "app/interfaces/api/rating_routes.py"
    "app/interfaces/dependencies.py"
)

for file in "${FILES[@]}"; do
    if python -m py_compile "$file" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file - Syntax error!"
        exit 1
    fi
done

echo ""
echo "Step 2: Import Check"
echo "--------------------"
echo "Verifying imports work correctly..."

python -c "
from app.core.config import get_settings
from app.core.sandbox_pool import SandboxPool
from app.domain.models.pressure import PressureLevel
from app.domain.services.agents.token_manager import TokenManager
from app.application.services.screenshot_service import ScreenshotCaptureService, ScreenshotCircuitBreaker
from app.infrastructure.observability.prometheus_metrics import (
    record_sandbox_health_check,
    record_sandbox_oom_kill,
    record_sandbox_runtime_crash,
)
from app.interfaces.api.rating_routes import submit_rating
print('${GREEN}✓${NC} All imports successful')
"

echo ""
echo "Step 3: Unit Tests"
echo "--------------------"
echo "Running unit tests for all priorities..."

# Browser tests (Priority 1)
echo ""
echo -e "${YELLOW}Priority 1: Browser Crash Prevention${NC}"
pytest tests/infrastructure/external/browser/test_proactive_heavy_page_detection.py -v --tb=short || true
pytest tests/infrastructure/external/browser/test_wikipedia_optimization.py -v --tb=short || true
pytest tests/infrastructure/external/browser/test_graceful_crash_degradation.py -v --tb=short || true
pytest tests/infrastructure/external/browser/test_memory_pressure.py -v --tb=short || true

# Screenshot tests (Priority 2)
echo ""
echo -e "${YELLOW}Priority 2: Screenshot Service Reliability${NC}"
pytest tests/application/services/test_screenshot_circuit_breaker.py -v --tb=short || true
pytest tests/application/services/test_screenshot_retry_backoff.py -v --tb=short || true

# Sandbox tests (Priority 3)
echo ""
echo -e "${YELLOW}Priority 3: Sandbox Health Monitoring${NC}"
pytest tests/core/test_sandbox_health_monitoring.py -v --tb=short || true
pytest tests/core/test_sandbox_oom_detection.py -v --tb=short || true

# Token tests (Priority 4)
echo ""
echo -e "${YELLOW}Priority 4: Token Management Optimization${NC}"
pytest tests/domain/services/agents/test_token_manager_new_thresholds.py -v --tb=short || true

# Security tests (Priority 6)
echo ""
echo -e "${YELLOW}Priority 6: Rating Endpoint Security${NC}"
pytest tests/interfaces/api/test_rating_endpoint_security.py -v --tb=short || true

echo ""
echo "Step 4: Integration Tests"
echo "--------------------"
echo "Running integration tests (may take longer)..."

pytest tests/integration/test_wikipedia_end_to_end.py -v --tb=short -m slow || true
pytest tests/integration/test_screenshot_pool_exhaustion.py -v --tb=short || true
pytest tests/integration/test_sandbox_oom_e2e.py -v --tb=short || true
pytest tests/integration/test_unauthorized_ratings_e2e.py -v --tb=short || true

echo ""
echo "Step 5: Metrics Verification"
echo "--------------------"
echo "Checking if new metrics are available in Prometheus..."

METRICS=(
    "pythinker_browser_heavy_page_detections_total"
    "pythinker_browser_wikipedia_summary_mode_total"
    "pythinker_browser_memory_pressure_total"
    "pythinker_browser_memory_restarts_total"
    "pythinker_screenshot_circuit_state"
    "pythinker_screenshot_retry_attempts_total"
    "pythinker_sandbox_health_check_total"
    "pythinker_sandbox_oom_kills_total"
    "pythinker_sandbox_runtime_crashes_total"
    "pythinker_token_pressure_level"
    "pythinker_rating_unauthorized_attempts_total"
)

for metric in "${METRICS[@]}"; do
    RESULT=$(docker exec pythinker-prometheus wget -qO- "http://localhost:9090/api/v1/query?query=$metric" 2>/dev/null)
    if echo "$RESULT" | grep -q "success"; then
        echo -e "${GREEN}✓${NC} $metric is available"
    else
        echo -e "${YELLOW}⚠${NC} $metric not found (may need backend restart)"
    fi
done

echo ""
echo "Step 6: Configuration Verification"
echo "--------------------"
echo "Checking new configuration settings..."

python -c "
from app.core.config import get_settings

settings = get_settings()

# Browser settings
assert hasattr(settings, 'browser_memory_critical_threshold_mb'), 'Missing: browser_memory_critical_threshold_mb'
assert hasattr(settings, 'browser_heavy_page_html_size_threshold'), 'Missing: browser_heavy_page_html_size_threshold'
assert hasattr(settings, 'browser_heavy_page_dom_threshold'), 'Missing: browser_heavy_page_dom_threshold'
assert hasattr(settings, 'browser_wikipedia_lightweight_mode'), 'Missing: browser_wikipedia_lightweight_mode'
assert hasattr(settings, 'browser_graceful_degradation'), 'Missing: browser_graceful_degradation'

# Screenshot settings
assert hasattr(settings, 'screenshot_circuit_breaker_enabled'), 'Missing: screenshot_circuit_breaker_enabled'
assert hasattr(settings, 'screenshot_max_consecutive_failures'), 'Missing: screenshot_max_consecutive_failures'
assert hasattr(settings, 'screenshot_circuit_recovery_seconds'), 'Missing: screenshot_circuit_recovery_seconds'
assert hasattr(settings, 'screenshot_http_retry_attempts'), 'Missing: screenshot_http_retry_attempts'
assert hasattr(settings, 'screenshot_http_retry_delay'), 'Missing: screenshot_http_retry_delay'

# Sandbox settings
assert hasattr(settings, 'sandbox_health_check_interval'), 'Missing: sandbox_health_check_interval'
assert hasattr(settings, 'sandbox_oom_monitor_enabled'), 'Missing: sandbox_oom_monitor_enabled'

# Token settings
assert hasattr(settings, 'token_safety_margin'), 'Missing: token_safety_margin'
assert hasattr(settings, 'token_early_warning_threshold'), 'Missing: token_early_warning_threshold'
assert hasattr(settings, 'token_critical_threshold'), 'Missing: token_critical_threshold'

print('${GREEN}✓${NC} All configuration settings present')
"

echo ""
echo "=========================================="
echo "Verification Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Syntax checks: All files valid"
echo "  - Import checks: All modules importable"
echo "  - Unit tests: See results above"
echo "  - Integration tests: See results above"
echo "  - Metrics: See availability above"
echo "  - Configuration: All settings present"
echo ""
echo "Next steps:"
echo "  1. Review any test failures above"
echo "  2. Check Grafana dashboards: http://localhost:3001"
echo "  3. Monitor logs: docker logs pythinker-backend-1 --tail 200"
echo ""
