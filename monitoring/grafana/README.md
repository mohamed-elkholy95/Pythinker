# Grafana Dashboards for Pythinker

This directory contains pre-configured Grafana dashboards for monitoring Pythinker components.

## Available Dashboards

### 1. Async Worker Dashboard (`pythinker-async-worker.json`)

**Purpose:** Monitor async job worker performance, health, and job queue metrics.

**Panels:**
- **Worker Health** - Real-time worker health status (1=healthy, 0=unhealthy)
- **Jobs In-Flight** - Current number of jobs being processed (capacity monitoring)
- **Dead Letter Queue** - Total jobs that exhausted retries
- **Job Success Rate** - Rolling 5-minute success rate (completed/dequeued)
- **Job Throughput** - Jobs processed per second (completed vs dequeued)
- **Job Processing Latency** - p50/p95/p99 percentiles for job duration
- **Job Failure Rate** - Failures per second by error type (stacked view)
- **Retry Distribution** - Retry attempts by attempt number
- **Job Dequeue Rate by Priority** - HIGH/NORMAL/LOW priority breakdown
- **Average Job Duration** - Mean processing time by priority

**Template Variables:**
- `queue` - Filter by queue name (e.g., "agent_tasks")
- `worker_id` - Filter by worker instance (e.g., "worker-1", "worker-2")

**Auto-refresh:** 10 seconds

**Time Range:** Last 1 hour (configurable)

---

### 2. Semantic Cache & Memory Dashboard (`pythinker-semantic-cache.json`)

**Purpose:** Monitor semantic cache hit rates, Qdrant query performance, and memory system metrics.

**Panels:**
- **Semantic Cache Hit Rate** - Cache effectiveness (5-minute rolling window)
- **Qdrant Query Latency** - p95/p99 vector search latency
- **Memory Budget Pressure** - Memory system load indicator
- **Evidence Rejection Rate** - Rate of rejected evidence claims
- **Checkpoint Write Frequency** - Memory checkpoint persistence rate

**Auto-refresh:** 10 seconds

**Time Range:** Last 6 hours (configurable)

---

## Quick Start

### 1. Import Dashboards to Grafana

**Option A: Grafana UI Import**

1. Open Grafana (http://localhost:3001)
2. Navigate to **Dashboards** → **Import**
3. Click **Upload JSON file**
4. Select dashboard file from this directory
5. Click **Import**

**Option B: Docker Volume Mount (Pre-provisioned)**

Add to `docker-compose-development.yml`:

```yaml
grafana:
  volumes:
    - ./monitoring/grafana:/etc/grafana/provisioning/dashboards:ro
```

Restart Grafana:
```bash
./dev.sh restart grafana
```

Dashboards will auto-load on startup.

---

### 2. Configure Prometheus Data Source

Grafana needs a Prometheus data source to query metrics.

**Automatic (Recommended):**

Create `monitoring/grafana/datasources/prometheus.yml`:

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

Mount in Grafana container:
```yaml
grafana:
  volumes:
    - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources:ro
```

**Manual:**

1. Open Grafana → **Configuration** → **Data Sources**
2. Click **Add data source**
3. Select **Prometheus**
4. Set URL: `http://prometheus:9090`
5. Click **Save & Test**

---

### 3. Verify Metrics Availability

Before using dashboards, verify that Prometheus is scraping worker metrics:

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="pythinker-backend")'

# Query worker health metric
curl -g 'http://localhost:9090/api/v1/query?query=pythinker_worker_health'

# Expected output:
# {
#   "status": "success",
#   "data": {
#     "resultType": "vector",
#     "result": [
#       {
#         "metric": {"worker_id": "worker-1"},
#         "value": [1234567890, "1"]
#       }
#     ]
#   }
# }
```

---

## Dashboard Customization

### Add Custom Panels

1. Open dashboard in Grafana
2. Click **Add panel** → **Add a new panel**
3. Configure query using available metrics (see below)
4. Save dashboard
5. Export JSON and commit to repo

### Available Worker Metrics

```promql
# Counters
pythinker_worker_jobs_dequeued_total{queue, priority}
pythinker_worker_jobs_completed_total{queue}
pythinker_worker_jobs_failed_total{queue, error_type}
pythinker_worker_jobs_retried_total{queue, attempt}
pythinker_worker_jobs_dead_letter_total{queue}

# Gauges
pythinker_worker_jobs_in_flight{queue}
pythinker_worker_health{worker_id}

# Histograms
pythinker_worker_job_processing_duration_seconds_bucket{queue, priority, le}
pythinker_worker_job_processing_duration_seconds_sum{queue, priority}
pythinker_worker_job_processing_duration_seconds_count{queue, priority}
```

### Example Queries

**Job success rate (5 minutes):**
```promql
rate(pythinker_worker_jobs_completed_total{queue="agent_tasks"}[5m])
  /
rate(pythinker_worker_jobs_dequeued_total{queue="agent_tasks"}[5m])
```

**p95 job latency:**
```promql
histogram_quantile(0.95,
  rate(pythinker_worker_job_processing_duration_seconds_bucket{queue="agent_tasks"}[5m])
)
```

**Dead letter queue growth rate:**
```promql
rate(pythinker_worker_jobs_dead_letter_total{queue="agent_tasks"}[5m])
```

---

## Alerting

### Recommended Alerts

**1. Worker Health Alert**

Trigger when worker becomes unhealthy:

```promql
pythinker_worker_health < 1
```

**Severity:** Critical
**Action:** Check worker logs, restart if needed

---

**2. High Failure Rate Alert**

Trigger when job failure rate exceeds 5%:

```promql
rate(pythinker_worker_jobs_failed_total[5m])
  /
rate(pythinker_worker_jobs_dequeued_total[5m]) > 0.05
```

**Severity:** Warning
**Action:** Investigate error types, check external dependencies

---

**3. Dead Letter Queue Growth Alert**

Trigger when DLQ accumulates jobs:

```promql
increase(pythinker_worker_jobs_dead_letter_total[1h]) > 10
```

**Severity:** Warning
**Action:** Investigate permanently failed jobs, consider manual intervention

---

**4. High Latency Alert**

Trigger when p95 latency exceeds 30 seconds:

```promql
histogram_quantile(0.95,
  rate(pythinker_worker_job_processing_duration_seconds_bucket[5m])
) > 30
```

**Severity:** Warning
**Action:** Check task execution performance, investigate slow tasks

---

**5. Worker Saturation Alert**

Trigger when worker approaches capacity:

```promql
pythinker_worker_jobs_in_flight / 5 > 0.8
```

**Severity:** Info
**Action:** Consider scaling workers horizontally

---

## Multi-Worker Monitoring

When running multiple worker instances (horizontal scaling), dashboards automatically aggregate metrics.

### Scale Workers

**Docker Compose:**
```bash
WORKER_REPLICAS=3 docker compose up -d
```

**Kubernetes:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pythinker-worker
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: worker
        image: pythinker/pythinker-backend:latest
        command: ["python", "-m", "app.workers.job_worker"]
        env:
        - name: WORKER_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
```

### View Per-Worker Metrics

Filter dashboard by worker ID using the template variable dropdown.

### Aggregate All Workers

Remove worker_id filter to see combined metrics across all instances.

---

## Troubleshooting

### Dashboard Shows No Data

**Check 1: Prometheus is scraping backend**

```bash
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="pythinker-backend")'
```

If backend is not in targets, add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'pythinker-backend'
    static_configs:
      - targets: ['backend:8000']
```

**Check 2: Worker is running**

```bash
docker ps | grep worker
docker logs pythinker-worker-1
```

**Check 3: Metrics endpoint is accessible**

```bash
curl http://localhost:8000/metrics | grep pythinker_worker
```

---

### High Memory Usage in Grafana

Reduce time range or disable auto-refresh for long-term monitoring.

**Dashboard settings:**
- Time range: Last 1 hour (instead of 24 hours)
- Auto-refresh: 30 seconds (instead of 10 seconds)

---

### Template Variable Shows No Options

Wait 10-30 seconds after worker starts for metrics to populate Prometheus.

Manually refresh template variable:
1. Dashboard settings → Variables → queue
2. Click refresh icon

---

## Production Deployment

### Grafana Persistence

Mount Grafana database to persist dashboards and settings:

```yaml
grafana:
  volumes:
    - grafana_data:/var/lib/grafana
```

### Authentication

Enable Grafana authentication in production:

```yaml
grafana:
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
    - GF_USERS_ALLOW_SIGN_UP=false
    - GF_AUTH_ANONYMOUS_ENABLED=false
```

### Grafana Provisioning

Auto-provision dashboards and data sources on startup:

```
monitoring/grafana/
├── dashboards/
│   ├── dashboard.yml          # Provisioning config
│   ├── pythinker-async-worker.json
│   └── pythinker-semantic-cache.json
└── datasources/
    └── prometheus.yml         # Prometheus datasource
```

**dashboard.yml:**
```yaml
apiVersion: 1

providers:
  - name: 'Pythinker Dashboards'
    orgId: 1
    folder: 'Pythinker'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

Mount in docker-compose:
```yaml
grafana:
  volumes:
    - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
    - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources:ro
```

---

## Contributing

When adding new dashboards:

1. Create dashboard in Grafana UI
2. Export dashboard JSON (Dashboard settings → JSON Model → Copy to clipboard)
3. Save to `monitoring/grafana/<dashboard-name>.json`
4. Update this README with dashboard description
5. Commit and push

**Dashboard Naming Convention:**
- Use kebab-case: `pythinker-component-name.json`
- Prefix with `pythinker-` for easy identification
- Use descriptive names (e.g., `pythinker-async-worker`, not `worker-dashboard`)

---

## Resources

- **Grafana Documentation:** https://grafana.com/docs/
- **Prometheus Query Language (PromQL):** https://prometheus.io/docs/prometheus/latest/querying/basics/
- **Histogram Quantiles:** https://prometheus.io/docs/practices/histograms/
- **Grafana Provisioning:** https://grafana.com/docs/grafana/latest/administration/provisioning/

---

## Support

For issues or questions:
- Check Grafana logs: `docker logs pythinker-grafana`
- Check Prometheus logs: `docker logs pythinker-prometheus`
- Verify metrics availability: `curl http://localhost:8000/metrics`
- Open issue on GitHub with dashboard JSON and error details
