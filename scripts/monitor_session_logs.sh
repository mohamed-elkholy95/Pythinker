#!/bin/bash
# Session Log Monitor
# Monitors Pythinker backend logs for validation, compression, and quality issues

echo "🔍 Pythinker Session Monitor"
echo "======================================"
echo ""

# Function to print section header
print_header() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Get container name
CONTAINER="pythinker-backend-1"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "❌ Error: Container ${CONTAINER} is not running"
    exit 1
fi

echo "✅ Container: ${CONTAINER} is running"
echo ""

# 1. Response Policy Decisions
print_header "📊 Response Policy Decisions (Last 10)"
docker logs ${CONTAINER} 2>&1 | \
    grep -E "Response policy:" | \
    tail -10 | \
    awk '{
        if (match($0, /mode=([a-z]+)/, m)) mode=m[1];
        if (match($0, /complexity=([0-9.]+)/, m)) comp=m[1];
        if (match($0, /risk=([0-9.]+)/, m)) risk=m[1];
        if (match($0, /confidence=([0-9.]+)/, m)) conf=m[1];
        if (match($0, /session_id=([a-zA-Z0-9]+)/, m)) sess=substr(m[1], 1, 12);
        print "  Mode:", mode, "| Complexity:", comp, "| Risk:", risk, "| Confidence:", conf, "| Session:", sess
    }'

# 2. Compression Activity
print_header "🗜️  Compression Activity"
COMPRESSION_COUNT=$(docker logs ${CONTAINER} 2>&1 | grep -c "compression")
echo "  Total compression mentions: ${COMPRESSION_COUNT}"

if [ ${COMPRESSION_COUNT} -eq 0 ]; then
    echo "  ℹ️  No compression activity detected"
    echo "  This is expected if max_chars was recently increased"
else
    echo ""
    echo "Recent compression events:"
    docker logs ${CONTAINER} 2>&1 | \
        grep -i "compression" | \
        tail -5
fi

# 3. Coverage Validation Issues
print_header "📋 Coverage Validation Issues (Last 10)"
COVERAGE_COUNT=$(docker logs ${CONTAINER} 2>&1 | grep -c "Summary coverage missing")
echo "  Total coverage warnings: ${COVERAGE_COUNT}"

if [ ${COVERAGE_COUNT} -gt 0 ]; then
    docker logs ${CONTAINER} 2>&1 | \
        grep "Summary coverage missing" | \
        tail -10 | \
        awk '{
            if (match($0, /missing required elements.*: (.+)$/, m)) missing=m[1];
            if (match($0, /session_id=([a-zA-Z0-9]+)/, m)) sess=substr(m[1], 1, 12);
            print "  ⚠️  Session:", sess, "| Missing:", missing
        }'
fi

# 4. Chain-of-Verification (CoVe) Activity
print_header "🔗 Chain-of-Verification (Last 10)"
COVE_COUNT=$(docker logs ${CONTAINER} 2>&1 | grep -c "CoVe:")
echo "  Total CoVe events: ${COVE_COUNT}"

if [ ${COVE_COUNT} -gt 0 ]; then
    docker logs ${CONTAINER} 2>&1 | \
        grep -E "CoVe:.*contradictions" | \
        tail -10 | \
        awk '{
            if (match($0, /Found ([0-9]+) contradictions, confidence: ([0-9.]+)/, m)) {
                count=m[1]; conf=m[2]
            }
            if (match($0, /session_id=([a-zA-Z0-9]+)/, m)) sess=substr(m[1], 1, 12);
            if (count != "") {
                status = (conf < 0.5) ? "🔴" : (conf < 0.8) ? "🟡" : "🟢"
                print "  " status " Session:", sess, "| Contradictions:", count, "| Confidence:", conf
                count=""
            }
        }'
fi

# 5. Critic Review Results
print_header "🎯 Critic Reviews (Last 10)"
CRITIC_COUNT=$(docker logs ${CONTAINER} 2>&1 | grep -c "Critic")
echo "  Total critic events: ${CRITIC_COUNT}"

if [ ${CRITIC_COUNT} -gt 0 ]; then
    docker logs ${CONTAINER} 2>&1 | \
        grep -E "(Critic reviewing|5-check result)" | \
        tail -10 | \
        awk '{
            if (match($0, /5-check result: (.+)$/, m)) result=m[1];
            if (match($0, /session_id=([a-zA-Z0-9]+)/, m)) sess=substr(m[1], 1, 12);
            if (result != "") {
                print "  ✓ Session:", sess, "|", result
                result=""
            }
        }'
fi

# 6. Step Execution Failures
print_header "⚠️  Step Execution Issues (Last 10)"
STUCK_COUNT=$(docker logs ${CONTAINER} 2>&1 | grep -c "stuck recovery exhausted")
BLOCKED_COUNT=$(docker logs ${CONTAINER} 2>&1 | grep -c "blocked steps")

echo "  Stuck recoveries exhausted: ${STUCK_COUNT}"
echo "  Blocked steps: ${BLOCKED_COUNT}"

if [ ${STUCK_COUNT} -gt 0 ] || [ ${BLOCKED_COUNT} -gt 0 ]; then
    docker logs ${CONTAINER} 2>&1 | \
        grep -E "(stuck recovery exhausted|blocked steps)" | \
        tail -10 | \
        awk '{
            if (match($0, /Step ([0-9]+) stuck recovery exhausted/, m)) {
                step=m[1]
                print "  🔴 Step", step, "stuck - recovery exhausted"
            }
            if (match($0, /([0-9]+) blocked steps/, m)) {
                count=m[1]
                print "  ⚠️ ", count, "steps blocked"
            }
        }'
fi

# 7. Recent Errors and Warnings
print_header "🚨 Recent Errors & Warnings (Last 10)"
docker logs ${CONTAINER} 2>&1 | \
    grep -E "\[(ERROR|WARNING)\]" | \
    tail -10 | \
    awk '{
        # Extract timestamp (first field)
        timestamp = $1
        # Extract level
        if (match($0, /\[([A-Z]+)\]/, m)) level = m[1]
        # Extract message (everything after the level)
        if (match($0, /\[([A-Z]+)\]\s+(.+)$/, m)) msg = substr(m[2], 1, 80)

        icon = (level == "ERROR") ? "🔴" : "🟡"
        print "  " icon, level ":", msg
    }'

# 8. Active Sessions
print_header "📌 Active Sessions (Last 5)"
docker logs ${CONTAINER} 2>&1 | \
    grep "Session.*started" | \
    tail -5 | \
    awk '{
        if (match($0, /Session ([a-zA-Z0-9]+) started/, m)) {
            sess=substr(m[1], 1, 16)
            if (match($0, /([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})/, t)) {
                time=t[1]
                print "  🔵 Session:", sess, "| Started:", time
            }
        }
    }'

# 9. Performance Metrics
print_header "⏱️  Performance (Last 5 Completions)"
docker logs ${CONTAINER} 2>&1 | \
    grep "completed in" | \
    tail -5 | \
    awk '{
        if (match($0, /completed in ([0-9.]+)ms/, m)) {
            time_ms = m[1]
            time_s = sprintf("%.1f", time_ms / 1000)
        }
        if (match($0, /events=([0-9]+)/, m)) events = m[1]
        if (match($0, /session_id=([a-zA-Z0-9]+)/, m)) sess=substr(m[1], 1, 12);
        if (time_s != "") {
            print "  ⏱  Session:", sess, "| Duration:", time_s "s | Events:", events
            time_s=""
        }
    }'

# Summary
print_header "📊 Summary"
echo "  Compression events: ${COMPRESSION_COUNT}"
echo "  Coverage warnings: ${COVERAGE_COUNT}"
echo "  CoVe verifications: ${COVE_COUNT}"
echo "  Critic reviews: ${CRITIC_COUNT}"
echo "  Stuck steps: ${STUCK_COUNT}"
echo "  Blocked steps: ${BLOCKED_COUNT}"
echo ""

# Recommendations
if [ ${COVERAGE_COUNT} -gt 10 ]; then
    echo "  💡 High coverage warnings - consider reviewing required sections"
fi

if [ ${STUCK_COUNT} -gt 5 ]; then
    echo "  💡 Many stuck steps - review agent execution logic"
fi

if [ ${COMPRESSION_COUNT} -eq 0 ]; then
    echo "  ✅ No compression detected - changes appear effective"
fi

echo ""
echo "======================================"
echo "Monitor complete at $(date)"
echo ""
echo "To follow logs in real-time:"
echo "  docker logs ${CONTAINER} --follow --tail 20"
echo ""
