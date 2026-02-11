# ✅ Monitoring Stack Setup Complete

**Date:** 2026-02-11 17:45
**Status:** 🟢 All Systems Operational

---

## 🎉 What's Running

Your complete monitoring stack is now **LIVE**:

| Service | URL | Status | Credentials |
|---------|-----|--------|-------------|
| **Grafana** | http://localhost:3001 | ✅ Running | admin / admin |
| **Prometheus** | http://localhost:9090 | ✅ Running | N/A |
| **Loki** | http://localhost:3100 | ✅ Running | N/A |
| **Promtail** | Internal | ✅ Running | N/A |

---

## 🚀 Quick Start - Debug Your Session

### Step 1: Open Grafana
```bash
open http://localhost:3001
```
- Username: `admin`
- Password: `admin`

### Step 2: View Pre-loaded Dashboards

Click **"Dashboards"** (4-squares icon) → You'll see:
1. **Pythinker Agent Monitoring** - Agent execution metrics
2. **Pythinker Logs Monitoring** - Real-time log analysis
3. **Pythinker System Monitoring** - System performance

### Step 3: Investigate Session 55e2c96dd93c4d57 (0/5 Tasks)

#### Using Grafana Logs:

1. Click **"Explore"** (compass icon)
2. Select **"Loki"** data source
3. Run this query:
```logql
{container_name="pythinker-backend-1"}
|= "55e2c96dd93c4d57"
|~ "Step 1|stuck|force-fail|tool|error"
```

4. Adjust time range to: **17:30 - 17:45 UTC**

#### Using Prometheus Metrics:

1. Open http://localhost:9090/graph
2. Query for stuck events:
```promql
increase(pythinker_agent_stuck_detections_total[1h])
```

3. Query for step failures:
```promql
pythinker_step_failures_total
```

4. Query for tool errors:
```promql
pythinker_tool_errors_total
```

---

## 🔍 What You Can Monitor Now

### Real-Time Metrics

**Agent Execution:**
- Active sessions count
- Stuck detection rate
- Step success/failure rates
- Recovery attempt counts

**Tool Performance:**
- Tool call rate
- Tool error rate
- Tool latency (p50, p95, p99)
- Tool timeout counts

**Validation System:**
- Compression attempts/rejections
- Coverage validation failures
- CoVe contradiction detection
- Critic review counts

**LLM Performance:**
- Request rate
- Token usage
- API latency
- Error rate

**System Health:**
- HTTP request rate
- Response times
- Memory usage
- Database connections

### Log Analysis

**Via Loki/Grafana:**
- Search logs by session ID
- Filter by severity (ERROR, WARNING, INFO)
- Real-time log tailing
- Log correlation with metrics

---

## 📊 Example Queries for Your Issue

### Find Why Step 1 Got Stuck

**Prometheus Query:**
```promql
# Was it a specific tool causing the issue?
topk(5, pythinker_tool_errors_total{session_id="55e2c96dd93c4d57"})
```

**Grafana/Loki Query:**
```logql
# See all tool calls in Step 1
{container_name="pythinker-backend-1"}
|= "55e2c96dd93c4d57"
|= "Step 1"
|~ "tool_started|tool_completed|tool_error"
```

### Check Search Tool Behavior

**Loki Query:**
```logql
{container_name="pythinker-backend-1"}
|= "55e2c96dd93c4d57"
|= "search"
```

### View Recovery Attempts

**Loki Query:**
```logql
{container_name="pythinker-backend-1"}
|= "55e2c96dd93c4d57"
|~ "recovery|retry|attempt"
```

---

## 🎯 Debugging Workflow

1. **Open Grafana:** http://localhost:3001

2. **Go to Explore**

3. **Set time range:** 17:30 - 17:45 UTC (when session ran)

4. **Query the session:**
   ```logql
   {container_name="pythinker-backend-1"} |= "55e2c96dd93c4d57"
   ```

5. **Look for patterns:**
   - Which tool was called when it stuck?
   - Were there API errors?
   - Did it timeout?
   - What was the recovery attempt sequence?

6. **Check metrics in Prometheus:**
   - Tool error rate during that time
   - LLM latency spikes
   - Network issues

---

## 🛠️ Management Commands

### Health Check
```bash
# Quick health check
bash scripts/check_monitoring.sh

# Individual checks
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3001/api/health # Grafana
curl http://localhost:3100/ready      # Loki
```

### View Logs
```bash
# Prometheus logs
docker logs pythinker-prometheus --follow

# Grafana logs
docker logs pythinker-grafana --follow

# All monitoring containers
docker compose -f docker-compose-monitoring.yml logs -f
```

### Restart Stack
```bash
# Restart all monitoring services
docker compose -f docker-compose-monitoring.yml restart

# Restart individual service
docker restart pythinker-grafana
```

### Stop Stack
```bash
# Stop but keep data
docker compose -f docker-compose-monitoring.yml stop

# Stop and remove (keeps volumes)
docker compose -f docker-compose-monitoring.yml down

# Stop and remove everything including data
docker compose -f docker-compose-monitoring.yml down -v
```

---

## 📈 Alert Rules

**Pre-configured alerts** (check Prometheus: http://localhost:9090/alerts):

1. **HighStuckDetectionRate**
   - Triggers when stuck detection rate > 0.1/second
   - Duration: 5 minutes

2. **HighStepFailureRate**
   - Triggers when step failure rate > 0.2/second
   - Duration: 5 minutes

3. **HighToolErrorRate**
   - Triggers when tool error rate > 10%
   - Duration: 2 minutes

4. **SlowLLMResponses**
   - Triggers when p95 LLM latency > 10s
   - Duration: 5 minutes

5. **HighCompressionRejectionRate**
   - Triggers when compression rejection > 0.5/second
   - Duration: 5 minutes

---

## 📚 Documentation Files Created

1. **`docs/monitoring/MONITORING_STACK_GUIDE.md`**
   - Complete monitoring guide
   - All available metrics
   - Query examples
   - Debugging workflows

2. **`scripts/check_monitoring.sh`**
   - Quick health check script
   - Shows current metric values
   - Verifies all endpoints

3. **`scripts/monitor_session_logs.sh`**
   - Session-specific log monitoring
   - Metrics aggregation
   - Issue detection

---

## 🎓 Next Steps

### 1. Familiarize Yourself with Grafana

- Explore the pre-loaded dashboards
- Try different time ranges
- Learn to use LogQL (Loki query language)

### 2. Set Up Custom Dashboards

- Create panels for your specific needs
- Save useful queries
- Set up auto-refresh

### 3. Configure Alerts

- Add your own alert rules in `prometheus/alert_rules.yml`
- Set up alert notifications (Slack, email, etc.)

### 4. Monitor Your Next Session

- Open Grafana before starting a session
- Watch metrics in real-time
- Correlate logs with metrics when issues occur

---

## 💡 Pro Tips

1. **Real-Time Monitoring:**
   - Set Grafana refresh to 5s when debugging
   - Use "Live" tail in log queries

2. **Correlate Data:**
   - Split view: metrics on top, logs on bottom
   - Use session_id to link everything

3. **Save Queries:**
   - Star useful queries in Grafana
   - Export dashboards as JSON

4. **Performance:**
   - Adjust scrape intervals in `prometheus/prometheus.yml`
   - Configure log retention in `loki/config.yml`

---

## 🔗 Quick Links

| Resource | URL |
|----------|-----|
| Grafana Dashboards | http://localhost:3001/dashboards |
| Grafana Explore | http://localhost:3001/explore |
| Prometheus Graph | http://localhost:9090/graph |
| Prometheus Targets | http://localhost:9090/targets |
| Prometheus Alerts | http://localhost:9090/alerts |
| Backend Metrics | http://localhost:8000/api/v1/metrics |

---

## ✅ Current Status Summary

```
✅ Prometheus:     Scraping metrics every 10s
✅ Grafana:        3 dashboards loaded
✅ Loki:           Collecting logs from backend
✅ Promtail:       Shipping Docker logs to Loki
✅ Alert Rules:    5 rules configured
✅ Backend Metrics: Exposing Prometheus format
```

---

## 🚨 Issues Found So Far

### Session 55e2c96dd93c4d57 Analysis

**Problem:** 0/5 tasks completed due to Step 1 stuck

**Next Debug Steps:**
1. Check tool error metrics in Prometheus
2. View Step 1 logs in Grafana/Loki
3. Identify which tool (search/browser) caused the stuck
4. Check if it was a timeout or API error

**Use Grafana NOW to investigate!**

---

**Setup Complete!** 🎉

**Access Grafana:** http://localhost:3001 (admin/admin)

Start debugging your 0/5 tasks issue with real-time metrics and logs!
