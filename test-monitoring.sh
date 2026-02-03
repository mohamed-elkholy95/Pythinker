#!/bin/bash
# Test script to verify monitoring pipeline

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       PYTHINKER MONITORING VERIFICATION                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

check_service() {
    local name=$1
    local url=$2
    if curl -s -f "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $name is running"
        return 0
    else
        echo -e "${RED}✗${NC} $name is NOT responding"
        return 1
    fi
}

echo "${BLUE}1. Checking Services...${NC}"
check_service "Backend" "http://localhost:8000/api/v1/metrics"
check_service "Prometheus" "http://localhost:9090/-/healthy"
check_service "Grafana" "http://localhost:3001/api/health"
check_service "Frontend" "http://localhost:5174"
echo ""

echo "${BLUE}2. Prometheus Scraping Status:${NC}"
curl -s http://localhost:9090/api/v1/targets | jq -r '.data.activeTargets[] |
    if .health == "up" then
        "✓ \(.labels.job): \(.health) (last scrape: \(.lastScrape | split(".")[0]))"
    else
        "✗ \(.labels.job): \(.health) - ERROR: \(.lastError)"
    end' | sed 's/^/  /'
echo ""

echo "${BLUE}3. Available Metrics in Prometheus:${NC}"
METRICS_COUNT=$(curl -s 'http://localhost:9090/api/v1/label/__name__/values' | jq -r '.data[] | select(startswith("pythinker"))' | wc -l | xargs)
echo "  Found $METRICS_COUNT Pythinker metrics"
curl -s 'http://localhost:9090/api/v1/label/__name__/values' | jq -r '.data[] | select(startswith("pythinker"))' | sed 's/^/    - /'
echo ""

echo "${BLUE}4. Grafana Datasource:${NC}"
curl -s -u admin:Debug-09912 http://localhost:3001/api/datasources/1 | jq -r '
    "  Name: \(.name)",
    "  URL: \(.url)",
    "  Type: \(.type)",
    "  Default: \(.isDefault)",
    "  Access: \(.access)"
'
echo ""

echo "${BLUE}5. Testing Prometheus → Grafana Connection:${NC}"
QUERY_STATUS=$(curl -s -u admin:Debug-09912 "http://localhost:3001/api/datasources/proxy/1/api/v1/query?query=up" | jq -r '.status')
if [ "$QUERY_STATUS" = "success" ]; then
    echo -e "  ${GREEN}✓${NC} Grafana can query Prometheus"
else
    echo -e "  ${RED}✗${NC} Grafana cannot query Prometheus (status: $QUERY_STATUS)"
fi
echo ""

echo "${BLUE}6. Current Metric Values:${NC}"
echo "  Active Sessions:"
curl -s 'http://localhost:9090/api/v1/query?query=pythinker_active_sessions' | jq -r '.data.result[].value[1]' | sed 's/^/    /' || echo "    (no data yet)"

echo "  Active Agents:"
curl -s 'http://localhost:9090/api/v1/query?query=pythinker_active_agents' | jq -r '.data.result[].value[1]' | sed 's/^/    /' || echo "    (no data yet)"

echo "  LLM Calls:"
LLM_COUNT=$(curl -s 'http://localhost:9090/api/v1/query?query=pythinker_llm_calls_total' | jq -r '.data.result | length')
if [ "$LLM_COUNT" -gt 0 ]; then
    curl -s 'http://localhost:9090/api/v1/query?query=pythinker_llm_calls_total' | jq -r '.data.result[] | "    \(.metric.model) (\(.metric.status)): \(.value[1])"'
else
    echo "    (no data yet - agent not executed)"
fi
echo ""

echo "${BLUE}7. Backend Metrics Endpoint:${NC}"
LINES=$(curl -s http://localhost:8000/api/v1/metrics | wc -l | xargs)
echo "  Total metric lines: $LINES"
if [ "$LINES" -lt 10 ]; then
    echo -e "  ${YELLOW}⚠${NC} Few metrics available - agent activity needed"
fi
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                        SUMMARY                                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
if [ "$METRICS_COUNT" -gt 0 ] && [ "$QUERY_STATUS" = "success" ]; then
    echo -e "${GREEN}✓ Monitoring is fully operational!${NC}"
    echo ""
    echo "Access points:"
    echo "  • Grafana:    http://localhost:3001 (admin/Debug-09912)"
    echo "  • Prometheus: http://localhost:9090"
    echo "  • Metrics:    http://localhost:8000/api/v1/metrics"
    echo ""
    echo "To generate metrics:"
    echo "  1. Open http://localhost:5174"
    echo "  2. Start a chat session"
    echo "  3. Send a message to the agent"
    echo "  4. Watch metrics populate in Grafana dashboard"
else
    echo -e "${YELLOW}⚠ Monitoring is partially operational${NC}"
    echo "Some metrics need agent activity to be populated"
fi
