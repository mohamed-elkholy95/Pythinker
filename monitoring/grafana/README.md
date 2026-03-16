# Grafana Dashboards for Pythinker

This directory contains pre-configured Grafana dashboards for monitoring Pythinker components.

## Available Dashboards

### 1. Semantic Cache & Memory Dashboard (`pythinker-semantic-cache.json`)

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

Before using dashboards, verify that Prometheus is scraping backend metrics:

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="pythinker-backend")'
```

---

## Dashboard Customization

### Add Custom Panels

1. Open dashboard in Grafana
2. Click **Add panel** → **Add a new panel**
3. Configure query using available metrics
4. Save dashboard
5. Export JSON and commit to repo

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

**Check 2: Metrics endpoint is accessible**

```bash
curl http://localhost:8000/metrics
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

---

## Resources

- **Grafana Documentation:** https://grafana.com/docs/
- **Prometheus Query Language (PromQL):** https://prometheus.io/docs/prometheus/latest/querying/basics/
- **Grafana Provisioning:** https://grafana.com/docs/grafana/latest/administration/provisioning/
