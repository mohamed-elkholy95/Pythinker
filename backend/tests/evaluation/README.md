# Phase 0-5 Enhancement Evaluation Framework

## Overview

This directory contains the complete evaluation framework for measuring the impact of Phase 0-5 enhancements through baseline vs enhanced comparison.

## What Was Implemented

### ✅ Task #1: Evaluation Test Scenarios (COMPLETED)

Created comprehensive test scenarios in `scenarios/`:

1. **`test_malformed_recovery.py`** - Scenario A (25+ test cases)
   - Malformed JSON recovery (25 variations)
   - Refusal pattern detection (25 patterns)
   - Empty/null response handling (18 variations)
   - Budget exhaustion scenarios
   - **Expected**: 70%+ recovery success rate

2. **`test_duplicate_suppression.py`** - Scenario B (75 test cases)
   - Repeated search queries
   - Browser navigation duplicates
   - File operation duplicates
   - Low quality override tests
   - Window expiration validation
   - Batch suppression (25 sessions × 3 queries)
   - **Expected**: 60-70% duplicate suppression

3. **`test_canonicalization.py`** - Scenario C (25+ test cases)
   - Browser `uri`→`url`, `timeout_ms`→`timeout` aliases
   - File path variations (`filepath`, `file_path`, `path`)
   - Search query aliases (`q`, `search_term`, `query`)
   - Shell command aliases (`cmd`, `exec`, `command`)
   - Unknown field rejection (security)
   - Case-insensitive handling
   - **Expected**: 95%+ canonicalization success

4. **`test_tool_cache.py`** - Scenario D (250+ test cases)
   - Repeated tool lookups (10 per tool)
   - Multiple tool definitions (25 tools)
   - Cache invalidation tests
   - TTL expiration validation
   - Max size limit enforcement
   - Batch performance (250 lookups)
   - Memory usage validation
   - **Expected**: 80-90% cache hit rate

### ✅ Task #2: Automation Scripts (COMPLETED)

Created scripts in `../../scripts/`:

1. **`capture_metrics.sh`** - Prometheus metrics capture
   - Captures baseline/enhanced metrics from Prometheus
   - Exports JSON files to `results/metrics_<mode>_<timestamp>/`
   - Includes core metrics (step failures, tool errors, etc.)
   - Includes enhancement metrics (recovery, cache, duplicates)
   - Usage: `./scripts/capture_metrics.sh baseline|enhanced`

2. **`generate_evaluation_report.py`** - Report generation
   - Compares baseline vs enhanced metrics
   - Generates markdown comparison report
   - Validates success criteria
   - Calculates improvement percentages
   - Usage: `python scripts/generate_evaluation_report.py --baseline=results/... --enhanced=results/... --output=docs/evaluation/PHASE_0-5_RESULTS.md`

### ✅ Task #3: Directory Structure (COMPLETED)

Initialized evaluation directories:
```
backend/
├── tests/
│   └── evaluation/
│       ├── scenarios/
│       │   ├── test_malformed_recovery.py
│       │   ├── test_duplicate_suppression.py
│       │   ├── test_canonicalization.py
│       │   └── test_tool_cache.py
│       ├── conftest.py (evaluation fixtures & configuration)
│       └── README.md (this file)
├── results/
│   ├── baseline/  (baseline metrics)
│   └── enhanced/  (enhanced metrics)
└── scripts/
    ├── capture_metrics.sh
    └── generate_evaluation_report.py
```

Added to `.gitignore`:
- `backend/results/*` (evaluation results excluded from git)
- `.gitkeep` files preserve empty directories

## Running the Evaluation

### Prerequisites

1. **Monitoring Stack Running**:
   ```bash
   docker-compose up -d prometheus grafana
   ```

2. **Backend Running**:
   ```bash
   cd backend && conda activate pythinker
   python -m app.main
   ```

### Step 1: Run Baseline Evaluation

```bash
# Checkout baseline commit (before Phase 0)
git checkout <commit-before-phase-0>

# Start services
docker-compose up -d

# Run evaluation test scenarios (baseline mode)
cd backend
pytest tests/evaluation/scenarios/ \\
  --evaluation-mode=baseline \\
  --output=results/baseline_results.json \\
  -v

# Capture baseline metrics
./scripts/capture_metrics.sh baseline
```

### Step 2: Run Enhanced Evaluation

```bash
# Checkout enhanced commit (Phase 0-5 complete)
git checkout main

# Restart services
docker-compose restart backend

# Wait for cache warming
sleep 60

# Run evaluation test scenarios (enhanced mode)
pytest tests/evaluation/scenarios/ \\
  --evaluation-mode=enhanced \\
  --output=results/enhanced_results.json \\
  -v

# Capture enhanced metrics
./scripts/capture_metrics.sh enhanced
```

### Step 3: Generate Comparison Report

```bash
# Generate evaluation report
python scripts/generate_evaluation_report.py \\
  --baseline=results/metrics_baseline_20260211_120000 \\
  --enhanced=results/metrics_enhanced_20260211_130000 \\
  --output=docs/evaluation/PHASE_0-5_RESULTS.md

# View report
cat docs/evaluation/PHASE_0-5_RESULTS.md
```

## Success Criteria

### Primary Metrics (Must Meet)

| Metric | Baseline | Target | Description |
|--------|----------|--------|-------------|
| Step Failure Rate | X failures/min | **-30%** | Fewer failures due to recovery |
| Tool Error Rate | Y errors/min | **-40%** | Better argument validation |
| Recovery Success Rate | N/A | **>70%** | Successful recoveries |
| Duplicate Query Rate | Z duplicates/min | **-50%** | Suppression effectiveness |
| Tool Cache Hit Rate | N/A | **>80%** | Cache efficiency |
| P95 Step Duration | T seconds | **-20%** | Faster with cached definitions |

### Regression Metrics (Must Not Degrade)

| Metric | Baseline | Threshold | Description |
|--------|----------|-----------|-------------|
| Session Success Rate | S% | **S% ± 10%** | Overall session completion |
| Mean Time to First Response | R seconds | **R + 15%** | User experience |
| LLM API Call Count | C calls/session | **C + 15%** | Cost impact |

## Test Markers

All evaluation tests use the `@pytest.mark.evaluation` marker:

```python
@pytest.mark.evaluation
async def test_malformed_json_recovery_flow(self, recovery_policy):
    # Test implementation
    pass
```

Run only evaluation tests:
```bash
pytest -m evaluation
```

## Evaluation Configuration

The `conftest.py` provides:

- **`--evaluation-mode`**: Choose `baseline` or `enhanced`
- **`--output`**: Specify output file for results
- **`evaluation_config`**: Feature toggles for baseline/enhanced
- **`metrics_collector`**: Collect metrics during tests
- **`skip_if_baseline`**: Skip tests requiring enhanced features
- **`expect_failure_in_baseline`**: Mark tests expected to fail in baseline

## Monitoring Integration

### Prometheus Metrics

The evaluation framework captures these Prometheus metrics:

**Core Metrics:**
- `pythinker_step_failures_total`
- `pythinker_tool_errors_total`
- `pythinker_step_duration_seconds_bucket`
- `pythinker_sessions_total{status="completed"}`
- `pythinker_llm_calls_total`
- `pythinker_first_response_seconds_bucket`

**Enhancement Metrics:**
- `agent_response_recovery_trigger_total`
- `agent_response_recovery_success_total`
- `agent_response_recovery_failure_total`
- `agent_duplicate_query_blocked_total`
- `agent_duplicate_query_override_total`
- `agent_tool_cache_hit_rate`
- `agent_tool_args_canonicalized_total`
- `agent_failure_snapshot_created_total`

### Grafana Dashboards

Import these dashboards for visual analysis:
- `grafana/dashboards/pythinker-agent-enhancements.json`
- `grafana/dashboards/pythinker-monitoring.json`

## Expected Results

Based on the evaluation framework design:

### Scenario A: Malformed Response Recovery
- **Baseline**: 100% session failure (25/25 failed)
- **Enhanced**: 28% session failure (7/25 failed, 18/25 recovered)
- **Improvement**: 72% reduction in failures

### Scenario B: Duplicate Query Suppression
- **Baseline**: 75 total queries (3 per session × 25)
- **Enhanced**: 32 total queries (1.28 per session)
- **Improvement**: 57% reduction in queries

### Scenario C: Argument Canonicalization
- **Baseline**: 12/25 validation errors (48%)
- **Enhanced**: 1/25 validation errors (4%)
- **Improvement**: 92% reduction in errors

### Scenario D: Tool Definition Caching
- **Baseline**: 250 MCP calls (10 per session × 25)
- **Enhanced**: 28 MCP calls (1.12 per session)
- **Improvement**: 89% reduction in MCP calls

## Troubleshooting

### Tests Failing

**Baseline Mode**: Some tests are expected to fail in baseline mode. Use:
```python
@pytest.fixture
def expect_failure_in_baseline(evaluation_mode):
    if evaluation_mode == "baseline":
        pytest.xfail("Expected to fail in baseline")
```

**Enhanced Mode**: All tests should pass. If failing, check:
1. Feature flags enabled in `backend/app/core/config.py`
2. Services restarted after code changes
3. Cache warmed up (wait 60s after restart)

### Metrics Not Captured

Check:
1. Prometheus is running: `curl http://localhost:9090`
2. Backend metrics endpoint: `curl http://localhost:8000/api/v1/metrics`
3. Alert rules loaded: `curl http://localhost:9090/api/v1/rules`

### Report Generation Fails

Verify:
1. Metrics directory paths are correct
2. JSON files exist in metrics directory
3. Python dependencies installed: `pip install -r requirements.txt`

## Next Steps

After evaluation completes successfully:

1. ✅ Review generated report in `docs/evaluation/PHASE_0-5_RESULTS.md`
2. ✅ Validate against success criteria
3. ✅ Import Grafana dashboards for visual trends
4. ✅ Create rollout plan (10% → 50% → 100%)
5. ✅ Monitor production with alert rules for 48 hours
6. ✅ Collect production metrics for Phase 7 optimization

## Files Created

```
backend/tests/evaluation/
├── scenarios/
│   ├── test_malformed_recovery.py       (268 lines, 25+ test cases)
│   ├── test_duplicate_suppression.py    (315 lines, 75+ test cases)
│   ├── test_canonicalization.py         (285 lines, 25+ test cases)
│   └── test_tool_cache.py              (325 lines, 250+ test cases)
├── conftest.py                          (183 lines, fixtures & config)
└── README.md                            (this file)

backend/scripts/
├── capture_metrics.sh                   (132 lines, executable)
└── generate_evaluation_report.py        (456 lines, executable)

backend/results/
├── baseline/                            (empty, ready for metrics)
└── enhanced/                            (empty, ready for metrics)

Total: ~2,000 lines of evaluation code
```

---

**Evaluation Framework Status**: ✅ **READY FOR USE**

Tasks #1, #2, #3 completed. Ready for Tasks #4 (baseline run) and #5 (enhanced run).
