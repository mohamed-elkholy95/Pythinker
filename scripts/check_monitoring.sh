#!/bin/bash
# Quick Monitoring Stack Health Check

echo "🔍 Pythinker Monitoring Stack Health Check"
echo "=========================================="
echo ""

# Check if containers are running
echo "📦 Container Status:"
docker ps --filter "name=pythinker-prometheus\|pythinker-grafana\|pythinker-loki\|pythinker-promtail" \
    --format "  {{.Names}}: {{.Status}}" 2>/dev/null || echo "  ❌ Monitoring stack not running"

echo ""

# Check endpoints
echo "🌐 Endpoint Health:"

# Prometheus
if curl -s -f http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "  ✅ Prometheus: http://localhost:9090"
else
    echo "  ❌ Prometheus: NOT ACCESSIBLE"
fi

# Grafana
if curl -s -f http://localhost:3001/api/health > /dev/null 2>&1; then
    echo "  ✅ Grafana: http://localhost:3001 (admin/admin)"
else
    echo "  ❌ Grafana: NOT ACCESSIBLE"
fi

# Loki
if curl -s -f http://localhost:3100/ready > /dev/null 2>&1; then
    echo "  ✅ Loki: http://localhost:3100"
else
    echo "  ❌ Loki: NOT ACCESSIBLE"
fi

# Backend Metrics
if curl -s -f http://localhost:8000/api/v1/metrics > /dev/null 2>&1; then
    echo "  ✅ Backend Metrics: http://localhost:8000/api/v1/metrics"
else
    echo "  ❌ Backend Metrics: NOT ACCESSIBLE"
fi

echo ""

# Show current key metrics
echo "📊 Current Metrics (Last Values):"
curl -s http://localhost:8000/api/v1/metrics 2>/dev/null | \
    grep -E "^pythinker_(active_sessions|agent_stuck|step_failures|tool_errors|compression_rejected)" | \
    grep -v "^#" | \
    awk '{
        metric = $1
        gsub(/pythinker_/, "", metric)
        value = $NF
        printf "  %-40s %s\n", metric ":", value
    }' | head -10

echo ""

# Prometheus targets
echo "🎯 Prometheus Scrape Targets:"
TARGETS=$(curl -s http://localhost:9090/api/v1/targets 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "$TARGETS" | grep -o '"job":"[^"]*"' | sort -u | sed 's/"job":"/  ✓ /' | sed 's/"$//'
else
    echo "  ⚠️  Unable to fetch targets"
fi

echo ""

# Quick links
echo "🔗 Quick Access:"
echo "  Grafana Dashboards: http://localhost:3001/dashboards"
echo "  Prometheus Graph:   http://localhost:9090/graph"
echo "  Prometheus Targets: http://localhost:9090/targets"
echo "  Loki (via Grafana): http://localhost:3001/explore"

echo ""
echo "📚 Documentation:"
echo "  Full Guide: docs/monitoring/MONITORING_STACK_GUIDE.md"

echo ""
