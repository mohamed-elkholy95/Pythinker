#!/bin/bash
# Test script for page refresh session persistence
# Tests that agent continues running when page is refreshed

set -e

echo "🧪 Testing Page Refresh Session Persistence"
echo "==========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Check services
echo -e "${YELLOW}Step 1: Checking services...${NC}"
if ! docker ps | grep -q pythinker-backend-1; then
    echo -e "${RED}❌ Backend not running${NC}"
    exit 1
fi
if ! docker ps | grep -q pythinker-mongodb-1; then
    echo -e "${RED}❌ MongoDB not running${NC}"
    exit 1
fi
echo -e "${GREEN}✅ All services running${NC}"
echo ""

# Step 2: Check for active sessions
echo -e "${YELLOW}Step 2: Checking for active sessions...${NC}"
ACTIVE_COUNT=$(docker exec pythinker-mongodb-1 mongosh --quiet pythinker --eval 'db.sessions.find({status: {$in: ["initializing", "running", "pending"]}}).count()' 2>/dev/null || echo "0")
echo "Active sessions: $ACTIVE_COUNT"
if [ "$ACTIVE_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Found $ACTIVE_COUNT active session(s)${NC}"
    docker exec pythinker-mongodb-1 mongosh --quiet pythinker --eval 'db.sessions.find({status: {$in: ["initializing", "running", "pending"]}}, {_id:1, status:1, sandbox_id:1})' 2>/dev/null
fi
echo ""

# Step 3: Check for sandbox containers
echo -e "${YELLOW}Step 3: Checking sandbox containers...${NC}"
SANDBOX_COUNT=$(docker ps -a --filter "name=sandbox" --format "{{.Names}}" | wc -l | tr -d ' ')
echo "Sandbox containers: $SANDBOX_COUNT"
if [ "$SANDBOX_COUNT" -gt 0 ]; then
    docker ps -a --filter "name=sandbox" --format "table {{.Names}}\t{{.Status}}\t{{.CreatedAt}}"
fi
echo ""

# Step 4: Check backend health
echo -e "${YELLOW}Step 4: Checking backend health...${NC}"
if curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend healthy${NC}"
else
    echo -e "${RED}❌ Backend not responding${NC}"
    exit 1
fi
echo ""

# Step 5: Check recent errors
echo -e "${YELLOW}Step 5: Checking for recent errors...${NC}"
ERROR_COUNT=$(docker logs pythinker-backend-1 --since 5m 2>&1 | grep -i "error" | grep -v "debug_error_string" | wc -l | tr -d ' ')
if [ "$ERROR_COUNT" -gt 0 ]; then
    echo -e "${RED}⚠️  Found $ERROR_COUNT error(s) in last 5 minutes${NC}"
    echo "Recent errors:"
    docker logs pythinker-backend-1 --since 5m 2>&1 | grep -i "error" | grep -v "debug_error_string" | tail -5
else
    echo -e "${GREEN}✅ No recent errors${NC}"
fi
echo ""

# Step 6: Manual test instructions
echo -e "${YELLOW}📋 Manual Test Steps:${NC}"
echo "1. Open browser: http://localhost:5174"
echo "2. Create new session and send message:"
echo "   'Search for Python best practices and create a summary'"
echo "3. Wait for agent to start executing (status: RUNNING)"
echo "4. Press F5 to refresh the page"
echo ""
echo -e "${YELLOW}Expected Behavior:${NC}"
echo "✅ Agent should continue running in background"
echo "✅ UI should reconnect automatically"
echo "✅ No duplicate messages in chat"
echo "✅ Tool panel shows correct state"
echo "✅ No errors in browser console"
echo ""
echo -e "${YELLOW}Check sessionStorage:${NC}"
echo "1. Open DevTools → Application → Session Storage"
echo "2. Look for key: pythinker-last-event-{sessionId}"
echo "3. Value should be the last event ID"
echo ""
echo -e "${YELLOW}Monitor logs in real-time:${NC}"
echo "docker logs -f pythinker-backend-1 | grep -E 'RESTORE|session.*running|duplicate'"
echo ""
echo "=========================================="
echo -e "${GREEN}✅ Pre-flight checks complete!${NC}"
echo "Ready for manual testing"
