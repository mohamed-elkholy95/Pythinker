#!/bin/bash
# Test script for frontend-backend connectivity fixes

set -e

echo "=========================================="
echo "Testing Pythinker Connectivity Fixes"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Health endpoint
echo "Test 1: Health Endpoint"
echo "------------------------"
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:8000/api/v1/health)
HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -1)
RESPONSE_BODY=$(echo "$HEALTH_RESPONSE" | head -1)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Health endpoint responding${NC}"
    echo "  Response: $RESPONSE_BODY"
else
    echo -e "${RED}✗ Health endpoint failed (HTTP $HTTP_CODE)${NC}"
    exit 1
fi
echo ""

# Test 2: CORS headers
echo "Test 2: CORS Configuration"
echo "------------------------"
CORS_RESPONSE=$(curl -s -I -H "Origin: http://localhost:5174" http://localhost:8000/api/v1/health | grep -i "access-control")

if echo "$CORS_RESPONSE" | grep -q "access-control-allow-origin"; then
    echo -e "${GREEN}✓ CORS properly configured${NC}"
    echo "$CORS_RESPONSE" | sed 's/^/  /'
else
    echo -e "${RED}✗ CORS headers missing${NC}"
    exit 1
fi
echo ""

# Test 3: Comprehensive health
echo "Test 3: Comprehensive Health Check"
echo "-----------------------------------"
COMP_HEALTH=$(curl -s http://localhost:8000/api/v1/monitoring/health)
if echo "$COMP_HEALTH" | grep -q "mongodb"; then
    echo -e "${GREEN}✓ Comprehensive health endpoint responding${NC}"
    echo "  Components: $(echo $COMP_HEALTH | grep -o '"[^"]*":' | wc -l) monitored"
else
    echo -e "${YELLOW}⚠ Comprehensive health endpoint may have issues${NC}"
fi
echo ""

# Test 4: Docker containers
echo "Test 4: Container Status"
echo "------------------------"
BACKEND_STATUS=$(docker ps --filter "name=pythinker-backend" --format "{{.Status}}" | head -1)
FRONTEND_STATUS=$(docker ps --filter "name=pythinker-frontend" --format "{{.Status}}" | head -1)

if echo "$BACKEND_STATUS" | grep -q "Up"; then
    echo -e "${GREEN}✓ Backend container running${NC} ($BACKEND_STATUS)"
else
    echo -e "${RED}✗ Backend container not running${NC}"
    exit 1
fi

if echo "$FRONTEND_STATUS" | grep -q "Up"; then
    echo -e "${GREEN}✓ Frontend container running${NC} ($FRONTEND_STATUS)"
else
    echo -e "${RED}✗ Frontend container not running${NC}"
    exit 1
fi
echo ""

# Test 5: Network connectivity
echo "Test 5: Inter-Container Network"
echo "--------------------------------"
NETWORK_TEST=$(docker exec pythinker-frontend-dev-1 node -e "
const http = require('http');
http.get('http://backend:8000/api/v1/health', (res) => {
  console.log('STATUS:', res.statusCode);
  process.exit(res.statusCode === 200 ? 0 : 1);
}).on('error', (e) => {
  console.error('ERROR:', e.message);
  process.exit(1);
});
" 2>&1)

if echo "$NETWORK_TEST" | grep -q "STATUS: 200"; then
    echo -e "${GREEN}✓ Frontend can reach backend via Docker network${NC}"
else
    echo -e "${YELLOW}⚠ Frontend-to-backend network may have issues${NC}"
    echo "  $NETWORK_TEST"
fi
echo ""

# Summary
echo "=========================================="
echo -e "${GREEN}All Critical Tests Passed!${NC}"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Open http://localhost:5174 in your browser"
echo "2. Check browser console for any errors"
echo "3. Test SSE reconnection by restarting backend:"
echo "   docker restart pythinker-backend-1"
echo ""
