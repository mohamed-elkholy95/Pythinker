#!/bin/bash
# Test script to verify browser window positioning in VNC

set -e

API_URL="http://localhost:8000/api/v1"
VNC_URL="http://localhost:5902"

echo "=============================================="
echo "Testing Browser Window Positioning in VNC"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Step 1: Creating a new session...${NC}"
SESSION_RESPONSE=$(curl -s -X PUT "${API_URL}/sessions" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "description": "Browser positioning test"
  }')

SESSION_ID=$(echo "$SESSION_RESPONSE" | grep -o '"session_id":"[^"]*' | cut -d'"' -f4)

if [ -z "$SESSION_ID" ]; then
  echo -e "${RED}❌ Failed to create session${NC}"
  echo "$SESSION_RESPONSE"
  exit 1
fi

echo -e "${GREEN}✓ Session created: $SESSION_ID${NC}"
echo ""

echo -e "${YELLOW}Step 2: Open VNC viewer to monitor browser positioning${NC}"
echo "VNC URL: vnc://localhost:5902"
echo "You should see the browser window centered in the display"
echo ""
echo "Press Enter when VNC viewer is ready..."
read

echo -e "${YELLOW}Step 3: Testing browser navigation (should stay centered)...${NC}"
echo ""

# Test 1: Initial navigation
echo "Test 1: Navigate to example.com..."
curl -s -X POST "${API_URL}/sessions/${SESSION_ID}/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Open example.com in the browser",
    "user_id": "test_user"
  }' > /dev/null &

CHAT_PID=$!
echo "Waiting for navigation..."
sleep 8
echo -e "${GREEN}✓ Check VNC - browser should be centered${NC}"
echo ""

# Test 2: Second navigation
echo "Test 2: Navigate to wikipedia.org..."
curl -s -X POST "${API_URL}/sessions/${SESSION_ID}/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Go to wikipedia.org",
    "user_id": "test_user"
  }' > /dev/null &

echo "Waiting for navigation..."
sleep 8
echo -e "${GREEN}✓ Check VNC - browser should still be centered${NC}"
echo ""

# Test 3: Browser restart (the critical test)
echo "Test 3: Restart browser (critical test for window positioning)..."
curl -s -X POST "${API_URL}/sessions/${SESSION_ID}/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Restart the browser and open github.com",
    "user_id": "test_user"
  }' > /dev/null &

echo "Waiting for browser restart..."
sleep 10
echo -e "${GREEN}✓ Check VNC - browser should STILL be centered after restart${NC}"
echo ""

# Test 4: Multiple operations
echo "Test 4: Multiple rapid navigations..."
for i in {1..3}; do
  echo "  Navigation $i/3..."
  curl -s -X POST "${API_URL}/sessions/${SESSION_ID}/chat" \
    -H "Content-Type: application/json" \
    -d "{
      \"message\": \"Navigate to example.com page $i\",
      \"user_id\": \"test_user\"
    }" > /dev/null &
  sleep 5
done

echo -e "${GREEN}✓ Check VNC - browser should remain centered${NC}"
echo ""

echo "=============================================="
echo "Manual Verification Checklist:"
echo "=============================================="
echo ""
echo "In your VNC viewer, verify:"
echo "  [ ] Browser window is centered at position 0,0"
echo "  [ ] All browser content is fully visible"
echo "  [ ] No part of the browser is cut off or shifted right"
echo "  [ ] Browser stayed centered through all operations"
echo "  [ ] Browser stayed centered after restart (most important!)"
echo ""
echo -e "${GREEN}If all checks pass, the fix is working correctly!${NC}"
echo ""

echo "Session ID: $SESSION_ID"
echo "Keep session active to continue testing, or press Ctrl+C to exit"

# Keep script running
wait
