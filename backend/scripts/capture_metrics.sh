#!/bin/bash
# scripts/capture_metrics.sh
# Captures Prometheus metrics for baseline or enhanced evaluation mode

set -euo pipefail

MODE=$1  # baseline or enhanced
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="results/metrics_${MODE}_${TIMESTAMP}"

# Validate mode argument
if [[ "$MODE" != "baseline" && "$MODE" != "enhanced" ]]; then
  echo "Error: MODE must be 'baseline' or 'enhanced'"
  echo "Usage: $0 <baseline|enhanced>"
  exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "Capturing $MODE metrics to $OUTPUT_DIR..."

# Prometheus URL
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

# Core metrics (always captured)
echo "  - Capturing step failures..."
curl -s -G "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=rate(pythinker_step_failures_total[1h])' \
  > "$OUTPUT_DIR/step_failures.json"

echo "  - Capturing tool errors..."
curl -s -G "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=rate(pythinker_tool_errors_total[1h])' \
  > "$OUTPUT_DIR/tool_errors.json"

echo "  - Capturing step duration P95..."
curl -s -G "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=histogram_quantile(0.95, rate(pythinker_step_duration_seconds_bucket[1h]))' \
  > "$OUTPUT_DIR/step_duration_p95.json"

echo "  - Capturing session success rate..."
curl -s -G "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=rate(pythinker_sessions_total{status="completed"}[1h]) / rate(pythinker_sessions_total[1h])' \
  > "$OUTPUT_DIR/session_success_rate.json"

echo "  - Capturing LLM API call count..."
curl -s -G "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=rate(pythinker_llm_calls_total[1h])' \
  > "$OUTPUT_DIR/llm_calls.json"

echo "  - Capturing mean time to first response..."
curl -s -G "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=histogram_quantile(0.50, rate(pythinker_first_response_seconds_bucket[1h]))' \
  > "$OUTPUT_DIR/mtfr.json"

# Enhancement metrics (only for enhanced mode)
if [ "$MODE" = "enhanced" ]; then
  echo "  - Capturing recovery triggers..."
  curl -s -G "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=rate(agent_response_recovery_trigger_total[1h])' \
    > "$OUTPUT_DIR/recovery_triggers.json"

  echo "  - Capturing recovery success rate..."
  curl -s -G "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=rate(agent_response_recovery_success_total[1h]) / (rate(agent_response_recovery_success_total[1h]) + rate(agent_response_recovery_failure_total[1h]))' \
    > "$OUTPUT_DIR/recovery_success_rate.json"

  echo "  - Capturing duplicate query blocks..."
  curl -s -G "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=rate(agent_duplicate_query_blocked_total[1h])' \
    > "$OUTPUT_DIR/duplicate_blocks.json"

  echo "  - Capturing duplicate suppression rate..."
  curl -s -G "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=rate(agent_duplicate_query_blocked_total[1h]) / (rate(agent_duplicate_query_blocked_total[1h]) + rate(agent_duplicate_query_override_total[1h]))' \
    > "$OUTPUT_DIR/duplicate_suppression_rate.json"

  echo "  - Capturing tool cache hit rate..."
  curl -s -G "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=agent_tool_cache_hit_rate{window="5m"}' \
    > "$OUTPUT_DIR/cache_hit_rate.json"

  echo "  - Capturing argument canonicalization..."
  curl -s -G "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=rate(agent_tool_args_canonicalized_total[1h])' \
    > "$OUTPUT_DIR/args_canonicalized.json"

  echo "  - Capturing recovery duration P95..."
  curl -s -G "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=histogram_quantile(0.95, rate(agent_response_recovery_duration_seconds_bucket[1h]))' \
    > "$OUTPUT_DIR/recovery_duration_p95.json"

  echo "  - Capturing snapshot generation rate..."
  curl -s -G "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=rate(agent_failure_snapshot_created_total[1h])' \
    > "$OUTPUT_DIR/snapshot_generation.json"
fi

# Create summary file
echo "Creating summary file..."
cat > "$OUTPUT_DIR/summary.txt" <<EOF
Evaluation Metrics Capture Summary
===================================
Mode: $MODE
Timestamp: $TIMESTAMP
Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Prometheus URL: $PROMETHEUS_URL

Files Captured:
EOF

ls -1 "$OUTPUT_DIR"/*.json | while read -r file; do
  echo "  - $(basename "$file")" >> "$OUTPUT_DIR/summary.txt"
done

echo ""
echo "✅ Metrics captured successfully!"
echo "   Output directory: $OUTPUT_DIR"
echo "   Files captured: $(ls -1 "$OUTPUT_DIR"/*.json | wc -l)"
echo ""
echo "Next steps:"
if [ "$MODE" = "baseline" ]; then
  echo "  1. Review baseline metrics"
  echo "  2. Deploy enhanced version"
  echo "  3. Run: $0 enhanced"
else
  echo "  1. Review enhanced metrics"
  echo "  2. Run: python scripts/generate_evaluation_report.py"
fi
