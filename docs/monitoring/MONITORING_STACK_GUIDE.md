# Pythinker Monitoring Stack Guide

**Status:** ✅ Running
**Date:** 2026-02-11

---

## 🎯 Monitoring Stack Overview

Your Pythinker monitoring stack is now **RUNNING** with:

| Component | Port | Status | Purpose |
|-----------|------|--------|---------|
| **Grafana** | 3001 | ✅ Healthy | Visualization dashboards |
| **Prometheus** | 9090 | ✅ Healthy | Metrics collection & storage |
| **Loki** | 3100 | ✅ Healthy | Log aggregation |
| **Promtail** | - | ✅ Running | Log shipping to Loki |

---

## 🌐 Access URLs

### **Grafana Dashboard**
- **URL:** http://localhost:3001
- **Username:** `admin`
- **Password:** `admin` (change on first login)
- **Pre-loaded Dashboards:**
  - Pythinker Agent Monitoring
  - Pythinker Logs Monitoring
  - Pythinker System Monitoring

### **Prometheus**
- **URL:** http://localhost:9090
- **Targets:** http://localhost:9090/targets
- **Graph Explorer:** http://localhost:9090/graph

### **Loki (via Grafana)**
- Access through Grafana's "Explore" tab
- Data source already configured

---

## 📊 Available Metrics

### Backend Metrics (Port 8000)

Prometheus is scraping metrics from: `http://backend:8000/api/v1/metrics`

**Key Metrics Available:**

```prometheus
# Session Metrics
pythinker_active_sessions               # Number of active sessions
pythinker_session_duration_seconds      # Session duration histogram
pythinker_session_messages_total        # Total messages per session

# Agent Metrics
pythinker_agent_executions_total        # Total agent executions
pythinker_agent_execution_duration_seconds  # Agent execution duration
pythinker_agent_stuck_detections_total  # Stuck detection count
pythinker_agent_stuck_recoveries_total  # Stuck recovery attempts

# Step Execution Metrics
pythinker_step_executions_total         # Total step executions
pythinker_step_failures_total           # Step failure count
pythinker_step_blocked_total            # Blocked steps count
pythinker_step_duration_seconds         # Step execution duration

# Tool Metrics
pythinker_tool_calls_total              # Total tool calls
pythinker_tool_call_duration_seconds    # Tool call duration
pythinker_tool_errors_total             # Tool error count

# Validation Metrics
pythinker_compression_attempts_total    # Compression attempts
pythinker_compression_rejected_total    # Compression rejections
pythinker_coverage_validation_failures_total  # Coverage validation failures
pythinker_cove_verifications_total      # CoVe verification runs
pythinker_cove_contradictions_total     # CoVe contradictions found
pythinker_critic_reviews_total          # Critic review count

# LLM Metrics
pythinker_llm_requests_total            # Total LLM API requests
pythinker_llm_tokens_total              # Token usage
pythinker_llm_errors_total              # LLM API errors
pythinker_llm_latency_seconds           # LLM response latency

# HTTP Metrics
pythinker_http_requests_total           # HTTP request count
pythinker_http_request_duration_seconds # HTTP request duration
pythinker_http_errors_total             # HTTP error count

# Screenshot Replay Metrics
pythinker_screenshot_captures_total             # Capture attempts by trigger/status
pythinker_screenshot_capture_latency_seconds    # Capture latency histogram
pythinker_screenshot_capture_size_bytes_total   # Captured bytes by trigger
pythinker_screenshot_fetch_total                # Replay fetches by access/status
pythinker_screenshot_fetch_latency_seconds      # Replay fetch latency histogram
pythinker_screenshot_fetch_size_bytes_total     # Served bytes by access
```

---

## 📈 Quick Queries for Debugging

### 1. **Check Stuck Step Rate**

In Prometheus (http://localhost:9090/graph):

```promql
# Stuck detection rate over last 5 minutes
rate(pythinker_agent_stuck_detections_total[5m])

# Total stuck steps in last hour
increase(pythinker_step_failures_total{reason="stuck"}[1h])

# Stuck recovery exhaustion rate
rate(pythinker_agent_stuck_recoveries_total{status="exhausted"}[5m])
```

### 2. **Step Execution Monitoring**

```promql
# Step failure rate by step
rate(pythinker_step_failures_total[5m])

# Average step duration
avg(pythinker_step_duration_seconds)

# Blocked steps count
sum(pythinker_step_blocked_total)

# Step success rate
rate(pythinker_step_executions_total{status="success"}[5m]) /
rate(pythinker_step_executions_total[5m])
```

### 3. **Validation & Compression Monitoring**

```promql
# Compression rejection rate
rate(pythinker_compression_rejected_total[5m])

# Coverage validation failures
increase(pythinker_coverage_validation_failures_total[1h])

# CoVe contradiction detection
rate(pythinker_cove_contradictions_total[5m])
```

### 4. **Tool Performance**

```promql
# Tool call rate by tool
rate(pythinker_tool_calls_total[5m])

# Tool error rate
rate(pythinker_tool_errors_total[5m]) / rate(pythinker_tool_calls_total[5m])

# Slowest tools (p95 latency)
histogram_quantile(0.95, rate(pythinker_tool_call_duration_seconds_bucket[5m]))
```

### 5. **LLM Performance**

```promql
# LLM request rate
rate(pythinker_llm_requests_total[5m])

# LLM token usage
rate(pythinker_llm_tokens_total[5m])

# LLM latency (p95)
histogram_quantile(0.95, rate(pythinker_llm_latency_seconds_bucket[5m]))

# LLM error rate
rate(pythinker_llm_errors_total[5m]) / rate(pythinker_llm_requests_total[5m])
```

---

## 🔍 Debugging Session 55e2c96dd93c4d57 (0/5 Tasks)

### Using Prometheus Queries

1. **Open Prometheus:** http://localhost:9090/graph

2. **Query stuck events:**
```promql
pythinker_agent_stuck_detections_total{session_id="55e2c96dd93c4d57"}
```

3. **Query step failures:**
```promql
pythinker_step_failures_total{session_id="55e2c96dd93c4d57"}
```

4. **Query tool errors:**
```promql
pythinker_tool_errors_total{session_id="55e2c96dd93c4d57"}
```

### Using Grafana Logs

1. **Open Grafana:** http://localhost:3001

2. **Go to "Explore"** (compass icon in left sidebar)

3. **Select "Loki" data source**

4. **Query logs for session:**
```logql
{container_name="pythinker-backend-1"}
|= "55e2c96dd93c4d57"
|= "stuck"
```

5. **Query tool errors:**
```logql
{container_name="pythinker-backend-1"}
|= "55e2c96dd93c4d57"
|~ "error|ERROR|failed"
```

---

## 📊 Pre-configured Dashboards

### 1. **Pythinker Agent Monitoring**
Shows:
- Active sessions
- Agent execution metrics
- Stuck detection rate
- Step success/failure rates
- Tool performance

### 2. **Pythinker Logs Monitoring**
Shows:
- Real-time log stream
- Error log count
- Warning log count
- Log volume by severity

### 3. **Pythinker System Monitoring**
Shows:
- HTTP request rate
- Response times
- LLM API performance
- Database connections

---

## 🚨 Alerts (Configured)

Check: `prometheus/alert_rules.yml`

**Active Alert Rules:**
- High stuck detection rate
- High step failure rate
- High tool error rate
- Slow LLM responses
- High compression rejection rate

**View Active Alerts:**
http://localhost:9090/alerts

---

## 🔧 Common Debugging Workflows

### Workflow 1: Debug Stuck Steps

1. **Check Prometheus for stuck rate:**
   ```promql
   rate(pythinker_agent_stuck_detections_total[5m])
   ```

2. **View logs in Grafana:**
   ```logql
   {container_name="pythinker-backend-1"} |~ "stuck|recovery"
   ```

3. **Check which tools are causing issues:**
   ```promql
   pythinker_tool_errors_total
   ```

4. **View tool call duration:**
   ```promql
   histogram_quantile(0.95, rate(pythinker_tool_call_duration_seconds_bucket[5m]))
   ```

### Workflow 2: Debug Validation Issues

1. **Check compression rejection rate:**
   ```promql
   rate(pythinker_compression_rejected_total[5m])
   ```

2. **View coverage validation failures:**
   ```promql
   pythinker_coverage_validation_failures_total
   ```

3. **Check CoVe contradictions:**
   ```promql
   rate(pythinker_cove_contradictions_total[5m])
   ```

4. **View validation logs:**
   ```logql
   {container_name="pythinker-backend-1"} |~ "compression|coverage|CoVe"
   ```

### Workflow 3: Debug Performance Issues

1. **Check overall request rate:**
   ```promql
   rate(pythinker_http_requests_total[5m])
   ```

2. **Check request duration (p95):**
   ```promql
   histogram_quantile(0.95, rate(pythinker_http_request_duration_seconds_bucket[5m]))
   ```

3. **Check LLM latency:**
   ```promql
   histogram_quantile(0.95, rate(pythinker_llm_latency_seconds_bucket[5m]))
   ```

4. **Check for slow tools:**
   ```promql
   topk(5, avg by (tool) (pythinker_tool_call_duration_seconds))
   ```

---

## 🎛️ Management Commands

### Start Monitoring Stack
```bash
docker compose -f docker-compose-development.yml -f docker-compose-monitoring.yml up -d
```

### Stop Monitoring Stack
```bash
docker compose -f docker-compose-monitoring.yml down
```

### Restart Monitoring Stack
```bash
docker compose -f docker-compose-monitoring.yml restart
```

### View Logs
```bash
# Prometheus logs
docker logs pythinker-prometheus --follow

# Grafana logs
docker logs pythinker-grafana --follow

# Loki logs
docker logs pythinker-loki --follow

# Promtail logs
docker logs pythinker-promtail --follow
```

### Check Health
```bash
# Prometheus health
curl http://localhost:9090/-/healthy

# Grafana health
curl http://localhost:3001/api/health

# Loki health
curl http://localhost:3100/ready
```

---

## 📝 Configuration Files

| File | Purpose |
|------|---------|
| `prometheus/prometheus.yml` | Prometheus scrape config |
| `prometheus/alert_rules.yml` | Alert rule definitions |
| `loki/config.yml` | Loki log aggregation config |
| `promtail/config.yml` | Promtail log shipping config |
| `grafana/provisioning/` | Auto-provisioned data sources |
| `grafana/dashboards/` | Pre-loaded dashboard definitions |

---

## 🔄 Data Retention

- **Prometheus:** 30 days (configurable in docker-compose-monitoring.yml)
- **Loki:** Configured in loki/config.yml
- **Grafana:** Persistent storage in docker volume

---

## 💡 Tips

1. **Real-time Monitoring:**
   - Use Grafana's "Auto-refresh" feature (top-right dropdown)
   - Set to 5s or 10s for real-time session monitoring

2. **Correlate Metrics & Logs:**
   - Use Grafana's "Split" view to see metrics and logs side-by-side
   - Add session_id to queries to correlate data

3. **Create Custom Queries:**
   - Save useful queries as favorites in Prometheus
   - Create custom panels in Grafana dashboards

4. **Export Data:**
   - Use Prometheus's `/api/v1/query` endpoint for programmatic access
   - Export Grafana dashboards as JSON for sharing

---

## 🎯 Next Steps for Debugging 0/5 Tasks Issue

1. **Open Grafana:** http://localhost:3001

2. **Navigate to "Pythinker Agent Monitoring" dashboard**

3. **Filter by time range** when the session occurred (17:36 - 17:38)

4. **Check:**
   - Stuck detection spike
   - Tool error rate
   - Step failure count

5. **Switch to "Explore" tab and query:**
   ```logql
   {container_name="pythinker-backend-1"}
   |= "55e2c96dd93c4d57"
   |~ "Step 1|stuck|force-fail"
   ```

6. **Look for patterns:**
   - Which tool was being called when it stuck?
   - Were there API errors?
   - Was there a timeout?

---

**Monitoring Stack Status:** ✅ **RUNNING**
**Access Grafana:** http://localhost:3001
**Access Prometheus:** http://localhost:9090

---

**Created:** 2026-02-11
**Last Updated:** 2026-02-11 17:45
