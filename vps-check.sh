#!/bin/bash
# VPS Health Check Script for Pythinker Deployment

echo "=========================================="
echo "   PYTHINKER VPS HEALTH CHECK"
echo "=========================================="
echo ""

# Get public IP
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || echo "Unable to detect")
echo "🌐 Public IP: $PUBLIC_IP"
echo ""

# System Resources
echo "=========================================="
echo "   SYSTEM RESOURCES"
echo "=========================================="
echo ""

echo "💾 Memory:"
free -h | grep -E "Mem|Swap"
echo ""

echo "💿 Disk Space:"
df -h / | grep -v Filesystem
echo ""

echo "🖥️  CPU Cores:"
nproc
echo ""

echo "⏱️  Load Average:"
uptime | awk -F'load average:' '{print $2}'
echo ""

# Docker Status
echo "=========================================="
echo "   DOCKER STATUS"
echo "=========================================="
echo ""

echo "🐳 Docker Version:"
docker --version
docker compose version
echo ""

echo "🏃 Running Containers:"
CONTAINER_COUNT=$(docker ps | wc -l)
echo "Total: $((CONTAINER_COUNT - 1)) containers"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -20
echo ""

# Dokploy Status
echo "=========================================="
echo "   DOKPLOY STATUS"
echo "=========================================="
echo ""

DOKPLOY_RUNNING=$(docker ps | grep dokploy | wc -l)
if [ $DOKPLOY_RUNNING -gt 0 ]; then
    echo "✅ Dokploy is running"
    docker ps | grep dokploy | awk '{print "   Container: " $NF}'
else
    echo "❌ Dokploy is not running"
fi
echo ""

# Pythinker Services
echo "=========================================="
echo "   PYTHINKER SERVICES"
echo "=========================================="
echo ""

PYTHINKER_COUNT=$(docker ps | grep pythinker | wc -l)
echo "🚀 Pythinker Containers: $PYTHINKER_COUNT / 12 expected"
echo ""

if [ $PYTHINKER_COUNT -gt 0 ]; then
    echo "Running services:"
    docker ps --filter "name=pythinker" --format "   ✅ {{.Names}} ({{.Status}})"
    echo ""
else
    echo "❌ No Pythinker containers running yet"
    echo ""
fi

# Check for any stopped/failed containers
STOPPED=$(docker ps -a --filter "name=pythinker" --filter "status=exited" --format "{{.Names}}" | wc -l)
if [ $STOPPED -gt 0 ]; then
    echo "⚠️  Stopped/Failed Containers:"
    docker ps -a --filter "name=pythinker" --filter "status=exited" --format "   ❌ {{.Names}} ({{.Status}})"
    echo ""
fi

# Network Check
echo "=========================================="
echo "   NETWORK STATUS"
echo "=========================================="
echo ""

NETWORK_EXISTS=$(docker network ls | grep pythinker | wc -l)
if [ $NETWORK_EXISTS -gt 0 ]; then
    echo "✅ Pythinker network exists"
    docker network ls | grep pythinker
else
    echo "⚠️  No pythinker network found (may not be deployed yet)"
fi
echo ""

# Volume Check
echo "=========================================="
echo "   VOLUME STATUS"
echo "=========================================="
echo ""

VOLUME_COUNT=$(docker volume ls | grep pythinker | wc -l)
echo "💾 Pythinker Volumes: $VOLUME_COUNT"
if [ $VOLUME_COUNT -gt 0 ]; then
    docker volume ls | grep pythinker
fi
echo ""

# Health Checks (only if services are running)
if [ $PYTHINKER_COUNT -gt 0 ]; then
    echo "=========================================="
    echo "   SERVICE HEALTH CHECKS"
    echo "=========================================="
    echo ""

    # Backend
    printf "🔧 Backend:      "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✅ Healthy (HTTP $HTTP_CODE)"
    else
        echo "❌ Not ready (HTTP $HTTP_CODE)"
    fi

    # Frontend
    printf "🎨 Frontend:     "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5174 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✅ Healthy (HTTP $HTTP_CODE)"
    else
        echo "❌ Not ready (HTTP $HTTP_CODE)"
    fi

    # Sandbox
    printf "📦 Sandbox:      "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8083/health 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✅ Healthy (HTTP $HTTP_CODE)"
    else
        echo "❌ Not ready (HTTP $HTTP_CODE)"
    fi

    # Grafana
    printf "📊 Grafana:      "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/api/health 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "✅ Healthy (HTTP $HTTP_CODE)"
    else
        echo "❌ Not ready (HTTP $HTTP_CODE)"
    fi

    echo ""
fi

# Access URLs
echo "=========================================="
echo "   ACCESS URLS"
echo "=========================================="
echo ""

if [ "$PUBLIC_IP" != "Unable to detect" ]; then
    echo "📱 Frontend:       http://$PUBLIC_IP:5174"
    echo "🔧 Backend API:    http://$PUBLIC_IP:8000/docs"
    echo "📊 Grafana:        http://$PUBLIC_IP:3001"
    echo "📈 Prometheus:     http://$PUBLIC_IP:9090"
    echo "💾 MinIO Console:  http://$PUBLIC_IP:9001"
else
    echo "⚠️  Could not detect public IP"
fi
echo ""

# Recent Logs Check
if [ $PYTHINKER_COUNT -gt 0 ]; then
    echo "=========================================="
    echo "   RECENT ERRORS (Last 2 minutes)"
    echo "=========================================="
    echo ""

    ERROR_COUNT=$(docker logs pythinker-backend-1 --since 2m 2>/dev/null | grep -i error | wc -l)
    if [ $ERROR_COUNT -gt 0 ]; then
        echo "⚠️  Found $ERROR_COUNT errors in backend logs (last 2 min)"
        echo "Run: docker logs pythinker-backend-1 --tail 50"
    else
        echo "✅ No recent errors detected"
    fi
    echo ""
fi

# Summary
echo "=========================================="
echo "   SUMMARY"
echo "=========================================="
echo ""

if [ $PYTHINKER_COUNT -eq 12 ]; then
    echo "✅ All 12 Pythinker containers running!"
    echo "✅ Deployment appears successful"
elif [ $PYTHINKER_COUNT -gt 0 ]; then
    echo "⚠️  Deployment in progress ($PYTHINKER_COUNT/12 containers up)"
    echo "⏳ Wait a few minutes and run this script again"
else
    echo "❌ Pythinker not deployed yet"
    echo "📝 Start deployment in Dokploy dashboard: http://$PUBLIC_IP:3000"
fi

echo ""
echo "=========================================="
echo ""

# Next steps
echo "📋 NEXT STEPS:"
if [ $PYTHINKER_COUNT -lt 12 ] && [ $PYTHINKER_COUNT -gt 0 ]; then
    echo "   1. Watch logs: docker compose -f /etc/dokploy/applications/pythinker*/code/docker-compose.dokploy.yml logs -f"
    echo "   2. Monitor containers: watch 'docker ps | grep pythinker'"
elif [ $PYTHINKER_COUNT -eq 12 ]; then
    echo "   1. Test the app: http://$PUBLIC_IP:5174"
    echo "   2. Check Grafana: http://$PUBLIC_IP:3001"
    echo "   3. Review logs if needed: docker logs pythinker-backend-1 -f"
else
    echo "   1. Go to Dokploy: http://$PUBLIC_IP:3000"
    echo "   2. Create Compose project (not Application!)"
    echo "   3. Repository: https://github.com/Planko123/Pythinker.git"
    echo "   4. Compose file: docker-compose.dokploy.yml"
    echo "   5. Add environment variables"
    echo "   6. Click Deploy"
fi

echo ""
