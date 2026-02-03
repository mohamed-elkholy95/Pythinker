# Pythinker Monitoring Setup

Complete monitoring solution for Pythinker AI Agent using Prometheus and Grafana.

## Architecture

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Backend   │────────▶│ Prometheus  │────────▶│   Grafana   │
│  (Metrics)  │  scrape │  (Storage)  │  query  │ (Dashboard) │
└─────────────┘         └─────────────┘         └─────────────┘
                              │
                              ▼
                        ┌─────────────┐
                        │    Alerts   │
                        └─────────────┘
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Backend Metrics | 8000/api/v1/metrics | Exposes Prometheus metrics |
| Prometheus | 9090 | Metrics storage and alerting |
| Grafana | 3001 | Visualization dashboards |

## Quick Start

### 1. Start Monitoring Stack

```bash
# Start alongside development stack
docker compose -f docker-compose-development.yml -f docker-compose-monitoring.yml up -d

# Or standalone
docker compose -f docker-compose-monitoring.yml up -d
```

### 2. Access Dashboards

- **Grafana**: http://localhost:3001
  - Username: `admin`
  - Password: `admin`

- **Prometheus**: http://localhost:9090
  - Targets: http://localhost:9090/targets
  - Alerts: http://localhost:9090/alerts
  - Rules: http://localhost:9090/rules

### 3. Import Dashboard

The main monitoring dashboard is auto-provisioned at:
- **Path**: `grafana/dashboards/pythinker-monitoring.json`
- **Title**: Pythinker AI Agent Monitoring
- **UID**: `pythinker-monitoring`

## Available Metrics

### Error Metrics

```promql
# Total errors by type and component
pythinker_errors_total{type="<error_type>", component="<component>"}

# Error types:
# - app_error: API exceptions
# - connection_pool_exhausted: Browser connection pool exhaustion
# - timeout: Request timeouts
# - unhandled_exception: Uncaught exceptions
```

### Session Metrics

```promql
# Active sessions
pythinker_active_sessions

# Active agents
pythinker_active_agents
```

### LLM Metrics

```promql
# Total LLM calls
pythinker_llm_calls_total{model="<model_name>", status="<success|error>"}

# LLM latency (histogram)
pythinker_llm_latency_seconds_bucket{model="<model_name>"}

# Token usage
pythinker_tokens_total{type="<prompt|completion|cached>"}
```

### Tool Metrics

```promql
# Tool executions
pythinker_tool_calls_total{tool="<tool_name>", status="<success|error>"}

# Tool latency (histogram)
pythinker_tool_latency_seconds_bucket{tool="<tool_name>"}
```

### Circuit Breaker Metrics

```promql
# Circuit breaker state (0=closed, 1=half_open, 2=open)
pythinker_circuit_breaker_state{name="<breaker_name>"}

# Circuit breaker calls
pythinker_circuit_breaker_calls_total{name="<breaker_name>", result="<success|failure|rejected>"}

# Adaptive circuit breaker failure rate
pythinker_circuit_breaker_failure_rate{name="<breaker_name>"}

# Adaptive circuit breaker failure threshold
pythinker_circuit_breaker_failure_threshold{name="<breaker_name>"}

# Circuit breaker recovery attempts
pythinker_circuit_breaker_recovery_total{name="<breaker_name>", result="<attempt|success|failure>"}

# Circuit breaker MTTR (histogram)
pythinker_circuit_breaker_mttr_seconds_bucket{name="<breaker_name>"}
```

### Concurrency Metrics

```promql
# Concurrent LLM requests
pythinker_llm_concurrent_requests

# LLM queue waiting
pythinker_llm_queue_waiting
```

### Cache Metrics

```promql
# Cache hits/misses
pythinker_cache_hits_total{cache_type="<embedding|reasoning|tool_result>"}
pythinker_cache_misses_total{cache_type="<embedding|reasoning|tool_result>"}

# Cache size
pythinker_cache_size{cache_type="<cache_type>"}
```

### Tool Tracing Metrics

```promql
# Tool tracing anomalies
pythinker_tool_trace_anomalies_total{tool="<tool_name>", type="<anomaly_type>"}
```

### Reward Hacking Detection Metrics

```promql
# Reward hacking signals (log-only detection)
pythinker_reward_hacking_signals_total{signal="<signal_type>", severity="<severity>"}
```

### Failure Prediction Metrics

```promql
# Failure prediction outcomes
pythinker_failure_prediction_total{result="<predicted|clear>"}

# Failure prediction probability (histogram)
pythinker_failure_prediction_probability_bucket{result="<predicted|clear>"}
```

## Dashboard Panels

### 1. Backend Status
- **Type**: Stat
- **Query**: `up{job="pythinker-backend"}`
- **Purpose**: Shows if backend is reachable

### 2. Active Sessions
- **Type**: Time Series
- **Query**: `pythinker_active_sessions`
- **Purpose**: Track concurrent session load

### 3. Total Errors
- **Type**: Stat
- **Query**: `sum(pythinker_errors_total)`
- **Purpose**: Overall error count

### 4. Errors by Type
- **Type**: Stacked Time Series
- **Query**: `pythinker_errors_total`
- **Purpose**: Error breakdown by type and component

### 5. Error Rate
- **Type**: Time Series
- **Query**: `rate(pythinker_errors_total[1m])`
- **Purpose**: Errors per minute

### 6. LLM Calls
- **Type**: Time Series
- **Query**: `pythinker_llm_calls_total`
- **Purpose**: Track LLM usage by model and status

### 7. Tool Calls
- **Type**: Time Series
- **Query**: `pythinker_tool_calls_total`
- **Purpose**: Track tool usage and failures

### 8. Token Usage
- **Type**: Stacked Time Series
- **Query**: `pythinker_tokens_total`
- **Purpose**: Monitor token consumption

### 9. Browser Connection Pool Errors
- **Type**: Time Series
- **Query**: `pythinker_errors_total{type="connection_pool_exhausted"}`
- **Purpose**: Track browser connection pool issues

## Alert Rules

### Critical Alerts

#### BackendDown
```yaml
expr: up{job="pythinker-backend"} == 0
for: 1m
severity: critical
```
Fires when backend service is unreachable.

#### BrowserConnectionPoolExhausted
```yaml
expr: increase(pythinker_errors_total{type="connection_pool_exhausted"}[5m]) > 0
for: 1m
severity: critical
```
Fires when browser connection pool is exhausted.

#### UnhandledExceptions
```yaml
expr: increase(pythinker_errors_total{type="unhandled_exception"}[5m]) > 0
for: 1m
severity: critical
```
Fires when unhandled exceptions occur.

### Warning Alerts

#### HighErrorRate
```yaml
expr: rate(pythinker_errors_total[5m]) > 0.1
for: 2m
severity: warning
```
Fires when error rate exceeds 0.1/sec.

#### HighTimeoutRate
```yaml
expr: rate(pythinker_errors_total{type="timeout"}[5m]) > 0.05
for: 3m
severity: warning
```
Fires when timeout rate is too high.

#### HighLLMErrorRate
```yaml
expr: sum(rate(pythinker_llm_calls_total{status="error"}[5m])) / sum(rate(pythinker_llm_calls_total[5m])) > 0.1
for: 3m
severity: warning
```
Fires when LLM error rate exceeds 10%.

## Common Queries

### Top Error Types
```promql
topk(5, sum by (type) (pythinker_errors_total))
```

### Error Rate by Component
```promql
sum by (component) (rate(pythinker_errors_total[5m]))
```

### LLM Success Rate
```promql
sum(pythinker_llm_calls_total{status="success"}) / sum(pythinker_llm_calls_total)
```

### Tool Success Rate
```promql
sum(pythinker_tool_calls_total{status="success"}) / sum(pythinker_tool_calls_total)
```

### Average LLM Latency (95th percentile)
```promql
histogram_quantile(0.95, rate(pythinker_llm_latency_seconds_bucket[5m]))
```

### Cache Hit Rate
```promql
sum(rate(pythinker_cache_hits_total[5m])) / (sum(rate(pythinker_cache_hits_total[5m])) + sum(rate(pythinker_cache_misses_total[5m])))
```

## Live Monitoring Commands

### Watch Metrics in Real-Time

```bash
# All error metrics
watch -n 2 'curl -s http://localhost:8000/api/v1/metrics | grep pythinker_errors'

# Active sessions
watch -n 1 'curl -s http://localhost:8000/api/v1/metrics | grep pythinker_active_sessions'

# All Pythinker metrics
watch -n 2 'curl -s http://localhost:8000/api/v1/metrics | grep "^pythinker_"'
```

### Monitor Logs

```bash
# Backend errors only
docker logs -f pythinker-backend-1 2>&1 | grep -i error

# Sandbox errors
docker logs -f pythinker-sandbox-1 2>&1 | grep -i error

# Prometheus errors
docker logs -f pythinker-prometheus 2>&1 | grep -i error

# Grafana errors
docker logs -f pythinker-grafana 2>&1 | grep -i error
```

### Query Prometheus API

```bash
# Current error count
curl -s 'http://localhost:9090/api/v1/query?query=pythinker_errors_total' | jq .

# Error rate (1 minute)
curl -s 'http://localhost:9090/api/v1/query?query=rate(pythinker_errors_total[1m])' | jq .

# Active alerts
curl -s http://localhost:9090/api/v1/alerts | jq .

# Alert rules
curl -s http://localhost:9090/api/v1/rules | jq .
```

## Troubleshooting

### No Metrics Appearing

1. **Check backend is exposing metrics:**
   ```bash
   curl http://localhost:8000/api/v1/metrics
   ```

2. **Check Prometheus targets:**
   ```bash
   curl -s http://localhost:9090/api/v1/targets | jq .
   ```

3. **Verify Prometheus is scraping:**
   ```bash
   docker logs pythinker-prometheus | grep -i scrape
   ```

### Dashboard Not Loading

1. **Check Grafana logs:**
   ```bash
   docker logs pythinker-grafana | tail -50
   ```

2. **Verify datasource connection:**
   ```bash
   curl -s -u admin:admin http://localhost:3001/api/datasources | jq .
   ```

3. **Restart Grafana:**
   ```bash
   docker restart pythinker-grafana
   ```

### Alerts Not Firing

1. **Check alert rules are loaded:**
   ```bash
   curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[].name'
   ```

2. **View alert status:**
   ```bash
   curl -s http://localhost:9090/api/v1/alerts | jq .
   ```

3. **Check Prometheus logs for rule evaluation errors:**
   ```bash
   docker logs pythinker-prometheus | grep -i rule
   ```

### Connection Pool Errors

If you see `connection_pool_exhausted` errors:

1. **Current pool size**: 8 connections per CDP URL
2. **Check pool usage:**
   ```bash
   docker logs pythinker-backend-1 | grep "Browser pool"
   ```

3. **Increase pool size** in `backend/app/core/config.py`:
   ```python
   browser_pool_max_per_url: int = 16  # Increase from 8
   ```

4. **Restart backend:**
   ```bash
   docker restart pythinker-backend-1
   ```

## Configuration Files

### Prometheus Configuration
- **Main config**: `prometheus/prometheus.yml`
- **Alert rules**: `prometheus/alert_rules.yml`
- **Scrape interval**: 10 seconds (backend), 15 seconds (default)
- **Retention**: 30 days

### Grafana Configuration
- **Datasource**: `grafana/provisioning/datasources/prometheus.yml`
- **Dashboard**: `grafana/provisioning/dashboards/default.yml`
- **Dashboard JSON**: `grafana/dashboards/pythinker-monitoring.json`

## Adding Custom Metrics

### 1. Define Metric

In `backend/app/infrastructure/observability/prometheus_metrics.py`:

```python
custom_metric = Counter(
    name="pythinker_custom_total",
    help_text="Custom metric description",
    labels=["label1", "label2"],
)
```

### 2. Register Metric

Add to `_metrics_registry`:

```python
_metrics_registry = [
    # ... existing metrics ...
    custom_metric,
]
```

### 3. Record Metric

```python
from app.infrastructure.observability.prometheus_metrics import custom_metric

custom_metric.inc({"label1": "value1", "label2": "value2"})
```

### 4. Create Dashboard Panel

Add panel to `grafana/dashboards/pythinker-monitoring.json` with query:
```promql
pythinker_custom_total{label1="value1"}
```

## Performance Tuning

### Prometheus

```yaml
# Adjust scrape interval for less frequent scraping
scrape_interval: 30s  # Default: 15s

# Reduce retention time
--storage.tsdb.retention.time=15d  # Default: 30d
```

### Grafana

```yaml
# Adjust refresh rate
refresh: "30s"  # Default: 10s in dashboard
```

### Backend

Error recording has minimal overhead (~0.1ms per error). No tuning needed.

## Security Notes

1. **Change Grafana password** in production:
   ```bash
   docker exec pythinker-grafana grafana cli admin reset-admin-password <new-password>
   ```

2. **Secure Prometheus** (add basic auth or network isolation)

3. **Restrict access** to monitoring ports (9090, 3001) via firewall

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboards](https://grafana.com/grafana/dashboards/)
