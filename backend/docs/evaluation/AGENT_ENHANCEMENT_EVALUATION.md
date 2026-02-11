# Agent Enhancement Evaluation Framework

**Purpose**: Measure the impact of Phases 0-5 enhancements through before/after comparison.

## Evaluation Methodology

### Baseline Capture (Before Enhancements)

1. **Environment Setup**:
   - Checkout commit before Phase 0 implementation
   - Deploy to isolated environment
   - Ensure monitoring stack is running

2. **Test Scenarios** (100+ sessions):
   - **Scenario A**: Malformed responses (25 sessions)
     - Trigger JSON parsing errors
     - Trigger refusal patterns
     - Trigger empty/null responses
   - **Scenario B**: Duplicate queries (25 sessions)
     - Repeated search queries within 5-minute window
     - Same browser navigation attempts
     - Identical file read operations
   - **Scenario C**: Tool argument variations (25 sessions)
     - Use alias argument names (`uri` vs `url`)
     - Include unknown fields
     - Mix canonical and alias forms
   - **Scenario D**: Tool definition lookups (25 sessions)
     - Repeated tool schema requests
     - MCP config changes mid-session
     - Cache invalidation scenarios

3. **Metrics Collection**:
   ```bash
   # Export baseline metrics
   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=rate(pythinker_step_failures_total[1h])' \
     > baseline_step_failures.json

   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=rate(pythinker_tool_errors_total[1h])' \
     > baseline_tool_errors.json

   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=histogram_quantile(0.95, rate(pythinker_step_duration_seconds_bucket[1h]))' \
     > baseline_step_duration_p95.json
   ```

### Enhanced Capture (After Enhancements)

1. **Environment Setup**:
   - Checkout commit with Phase 0-5 complete
   - Deploy to same environment
   - Feature flags enabled: all enhancements ON

2. **Test Scenarios** (Same 100+ sessions):
   - Run identical test scenarios as baseline
   - Ensure same user inputs, tool calls, session flows

3. **Metrics Collection**:
   ```bash
   # Export enhanced metrics (same queries)
   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=rate(pythinker_step_failures_total[1h])' \
     > enhanced_step_failures.json

   # Plus new enhancement metrics
   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=rate(agent_response_recovery_trigger_total[1h])' \
     > enhanced_recovery_triggers.json

   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=rate(agent_duplicate_query_blocked_total[1h])' \
     > enhanced_duplicate_blocks.json

   curl -G http://localhost:9090/api/v1/query \
     --data-urlencode 'query=agent_tool_cache_hit_rate{window="5m"}' \
     > enhanced_cache_hit_rate.json
   ```

## Evaluation Metrics

### Primary Metrics (Expected Improvements)

| Metric | Baseline | Target | Description |
|--------|----------|--------|-------------|
| **Step Failure Rate** | X failures/min | -30% | Fewer failures due to recovery |
| **Tool Error Rate** | Y errors/min | -40% | Better argument validation |
| **Recovery Success Rate** | N/A | >70% | New metric - successful recoveries |
| **Duplicate Query Rate** | Z duplicates/min | -50% | Suppression effectiveness |
| **Tool Cache Hit Rate** | N/A | >80% | New metric - cache efficiency |
| **P95 Step Duration** | T seconds | -20% | Faster with cached definitions |

### Secondary Metrics (Side Effects)

| Metric | Watch For | Description |
|--------|-----------|-------------|
| **Recovery Overhead** | <500ms P95 | Time spent in recovery flow |
| **Snapshot Generation** | <2/min | Frequency of snapshot creation |
| **Cache Memory** | <10MB | Memory footprint of cache |
| **Canonicalization Rate** | Matches alias usage | Arguments canonicalized |

### Regression Metrics (Must Not Degrade)

| Metric | Baseline | Threshold | Description |
|--------|----------|-----------|-------------|
| **Session Success Rate** | S% | S% ± 5% | Overall session completion |
| **Mean Time to First Response** | R seconds | R + 10% | User experience |
| **LLM API Call Count** | C calls/session | C + 15% | Cost impact |

## Evaluation Scenarios

### Scenario A: Malformed Response Recovery

**Setup**:
```python
# tests/evaluation/scenarios/test_malformed_recovery.py
import pytest
from app.domain.services.agents.response_recovery import ResponseRecoveryPolicy

@pytest.mark.evaluation
async def test_malformed_json_recovery():
    """Evaluate recovery from malformed JSON responses."""
    # Inject malformed response
    malformed = '{"tool": "search", "args": {"query": "test"'  # Incomplete

    # Before: session fails immediately
    # After: recovery triggered, retry succeeds

    # Metrics to collect:
    # - agent_response_recovery_trigger_total{recovery_reason="malformed_output"}
    # - agent_response_recovery_success_total
    # - pythinker_step_failures_total (should decrease)
```

**Expected Results**:
- Baseline: 100% session failure on malformed JSON
- Enhanced: <30% session failure (70%+ recovery success)

### Scenario B: Duplicate Query Suppression

**Setup**:
```python
# tests/evaluation/scenarios/test_duplicate_suppression.py
@pytest.mark.evaluation
async def test_repeated_search_suppression():
    """Evaluate duplicate query suppression effectiveness."""
    # Execute same search query 3 times within 5 minutes
    for i in range(3):
        await agent.search(query="machine learning tutorials", limit=10)
        await asyncio.sleep(60)  # 1 minute apart

    # Before: 3 API calls to search service
    # After: 1 API call (2 suppressed)

    # Metrics to collect:
    # - agent_duplicate_query_blocked_total
    # - search_tool_executions_total (should decrease)
```

**Expected Results**:
- Baseline: 100% duplicate queries executed
- Enhanced: 60-70% duplicates suppressed (within window, high quality)

### Scenario C: Argument Canonicalization

**Setup**:
```python
# tests/evaluation/scenarios/test_canonicalization.py
@pytest.mark.evaluation
async def test_alias_argument_handling():
    """Evaluate argument alias canonicalization."""
    # Use alias argument names
    await agent.browser(uri="https://example.com", timeout_ms=5000)

    # Before: ValidationError (unknown fields 'uri', 'timeout_ms')
    # After: Canonicalized to 'url', 'timeout' - success

    # Metrics to collect:
    # - agent_tool_args_canonicalized_total
    # - pythinker_tool_errors_total{error_type="validation"} (should decrease)
```

**Expected Results**:
- Baseline: 50-60% tool errors due to alias usage
- Enhanced: <5% tool errors (95%+ canonicalization success)

### Scenario D: Tool Definition Caching

**Setup**:
```python
# tests/evaluation/scenarios/test_tool_cache.py
@pytest.mark.evaluation
async def test_repeated_tool_lookups():
    """Evaluate tool definition cache hit rate."""
    # Request same tool definition 10 times
    for i in range(10):
        definition = await tool_registry.get_definition("browser")
        await asyncio.sleep(1)

    # Before: 10 MCP calls
    # After: 1 MCP call (9 cache hits)

    # Metrics to collect:
    # - agent_tool_definition_cache_hits_total
    # - agent_tool_definition_cache_misses_total
    # - agent_tool_cache_hit_rate
```

**Expected Results**:
- Baseline: 0% cache hit rate (no cache)
- Enhanced: 80-90% cache hit rate

## Running Evaluation

### 1. Setup Evaluation Environment

```bash
# Create evaluation branch
git checkout -b evaluation/phase-0-5

# Deploy baseline
git checkout <commit-before-phase-0>
docker-compose -f docker-compose-evaluation.yml up -d

# Wait for stability
sleep 30
```

### 2. Run Baseline Tests

```bash
# Execute evaluation scenarios (baseline)
cd backend
pytest tests/evaluation/scenarios/ \
  --evaluation-mode=baseline \
  --output=results/baseline_results.json \
  -v

# Capture baseline metrics
./scripts/capture_metrics.sh baseline
```

### 3. Deploy Enhanced Version

```bash
# Deploy enhanced
git checkout main  # Or phase-0-5 completion commit
docker-compose -f docker-compose-evaluation.yml restart backend

# Wait for cache warming
sleep 60
```

### 4. Run Enhanced Tests

```bash
# Execute evaluation scenarios (enhanced)
pytest tests/evaluation/scenarios/ \
  --evaluation-mode=enhanced \
  --output=results/enhanced_results.json \
  -v

# Capture enhanced metrics
./scripts/capture_metrics.sh enhanced
```

### 5. Generate Comparison Report

```bash
# Generate evaluation report
python scripts/generate_evaluation_report.py \
  --baseline=results/baseline_results.json \
  --enhanced=results/enhanced_results.json \
  --output=docs/evaluation/PHASE_0-5_RESULTS.md
```

## Evaluation Report Template

```markdown
# Phase 0-5 Enhancement Evaluation Results

**Date**: YYYY-MM-DD
**Baseline Commit**: <commit-hash>
**Enhanced Commit**: <commit-hash>
**Test Sessions**: 100 (25 per scenario)

## Summary

| Category | Baseline | Enhanced | Improvement |
|----------|----------|----------|-------------|
| Step Failure Rate | X/min | Y/min | -Z% ✅ |
| Tool Error Rate | A/min | B/min | -C% ✅ |
| Recovery Success | N/A | D% | NEW ✅ |
| Duplicate Suppression | 0% | E% | +E% ✅ |
| Cache Hit Rate | 0% | F% | +F% ✅ |
| P95 Step Duration | G sec | H sec | -I% ✅ |

## Detailed Results

### Scenario A: Malformed Response Recovery
- **Baseline**: 100% session failure (25/25 failed)
- **Enhanced**: 28% session failure (7/25 failed, 18/25 recovered)
- **Improvement**: 72% reduction in failures
- **Recovery Metrics**:
  - Triggers: 25/25 (100% detection)
  - Successes: 18/25 (72% success rate)
  - P95 Duration: 1.2 seconds
  - Budget Exhausted: 7/25 (28%)

### Scenario B: Duplicate Query Suppression
- **Baseline**: 75 total queries (3 per session × 25)
- **Enhanced**: 32 total queries (1.28 per session)
- **Improvement**: 57% reduction in queries
- **Suppression Metrics**:
  - Blocked: 43/75 (57%)
  - Override (low quality): 0/75 (0%)
  - Override (explicit retry): 0/75 (0%)

### Scenario C: Argument Canonicalization
- **Baseline**: 12/25 validation errors (48%)
- **Enhanced**: 1/25 validation errors (4%)
- **Improvement**: 92% reduction in errors
- **Canonicalization Metrics**:
  - Arguments canonicalized: 48/50 (96%)
  - Unknown fields rejected: 2/50 (4% - security test)

### Scenario D: Tool Definition Caching
- **Baseline**: 250 MCP calls (10 per session × 25)
- **Enhanced**: 28 MCP calls (1.12 per session)
- **Improvement**: 89% reduction in MCP calls
- **Cache Metrics**:
  - Hit Rate: 88.8%
  - P95 Lookup Duration: 0.8ms (hit), 42ms (miss)
  - Memory Usage: 6.2 KB

## Regression Analysis

| Metric | Baseline | Enhanced | Change | Status |
|--------|----------|----------|--------|--------|
| Session Success Rate | 82% | 85% | +3% | ✅ PASS |
| MTFR (Mean Time to First Response) | 2.1s | 2.3s | +9% | ✅ PASS |
| LLM API Calls per Session | 12.4 | 13.1 | +6% | ✅ PASS |

All regression metrics within acceptable thresholds.

## Conclusion

✅ **All primary objectives achieved**
✅ **No significant regressions detected**
✅ **Ready for production deployment**

### Key Wins
1. 72% reduction in session failures due to malformed responses
2. 57% reduction in duplicate tool executions
3. 92% reduction in tool validation errors
4. 89% reduction in MCP API calls

### Recommended Next Steps
1. Enable enhancements in production with feature flags
2. Monitor alert rules for 48 hours
3. Gradually increase rollout percentage
4. Collect production metrics for Phase 7 optimization
```

## Automation Scripts

### Capture Metrics Script

```bash
#!/bin/bash
# scripts/capture_metrics.sh

MODE=$1  # baseline or enhanced
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="results/metrics_${MODE}_${TIMESTAMP}"

mkdir -p "$OUTPUT_DIR"

# Core metrics
curl -G http://localhost:9090/api/v1/query \
  --data-urlencode 'query=rate(pythinker_step_failures_total[1h])' \
  > "$OUTPUT_DIR/step_failures.json"

curl -G http://localhost:9090/api/v1/query \
  --data-urlencode 'query=rate(pythinker_tool_errors_total[1h])' \
  > "$OUTPUT_DIR/tool_errors.json"

# Enhancement metrics (if enhanced mode)
if [ "$MODE" = "enhanced" ]; then
  curl -G http://localhost:9090/api/v1/query \
    --data-urlencode 'query=rate(agent_response_recovery_trigger_total[1h])' \
    > "$OUTPUT_DIR/recovery_triggers.json"

  curl -G http://localhost:9090/api/v1/query \
    --data-urlencode 'query=agent_tool_cache_hit_rate{window="5m"}' \
    > "$OUTPUT_DIR/cache_hit_rate.json"
fi

echo "Metrics captured to $OUTPUT_DIR"
```

### Generate Report Script

```python
#!/usr/bin/env python3
# scripts/generate_evaluation_report.py

import json
import sys
from pathlib import Path
from datetime import datetime

def generate_report(baseline_file, enhanced_file, output_file):
    """Generate evaluation comparison report."""

    # Load results
    with open(baseline_file) as f:
        baseline = json.load(f)

    with open(enhanced_file) as f:
        enhanced = json.load(f)

    # Calculate improvements
    improvements = calculate_improvements(baseline, enhanced)

    # Generate markdown report
    report = f"""# Phase 0-5 Enhancement Evaluation Results

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Baseline File**: {baseline_file}
**Enhanced File**: {enhanced_file}

## Summary

{generate_summary_table(improvements)}

## Detailed Results

{generate_detailed_results(baseline, enhanced, improvements)}

## Conclusion

{generate_conclusion(improvements)}
"""

    # Write report
    Path(output_file).write_text(report)
    print(f"Report generated: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: generate_evaluation_report.py <baseline.json> <enhanced.json> <output.md>")
        sys.exit(1)

    generate_report(sys.argv[1], sys.argv[2], sys.argv[3])
```

## Success Criteria

Evaluation is considered successful if:

1. **Primary Metrics**:
   - ✅ Step failure rate reduced by ≥25%
   - ✅ Recovery success rate ≥65%
   - ✅ Duplicate suppression rate ≥50%
   - ✅ Cache hit rate ≥75%

2. **Regression Metrics**:
   - ✅ Session success rate within ±10%
   - ✅ MTFR increase ≤15%
   - ✅ LLM API call increase ≤20%

3. **Quality Metrics**:
   - ✅ No P1/P0 bugs introduced
   - ✅ All unit tests passing
   - ✅ Integration tests ≥95% passing
   - ✅ Alert rules validated

## Next Steps After Evaluation

1. **Document Results**: Update `PHASE_0-5_RESULTS.md` with actual numbers
2. **Create Rollout Plan**: Gradual feature flag rollout (10% → 50% → 100%)
3. **Monitor Production**: 48-hour observation period with alerts
4. **Optimize Based on Data**: Use production metrics for Phase 7 improvements
5. **Knowledge Transfer**: Share results with team, update runbooks
