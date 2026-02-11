# Monitoring Stack Quick Reference Card

**Always check these when debugging ANY issue!**

---

## 🚀 Quick Access URLs

```
Grafana:    http://localhost:3001  (admin/admin)
Prometheus: http://localhost:9090
Loki:       http://localhost:3100
Metrics:    http://localhost:8000/api/v1/metrics
```

---

## 🔍 Essential Debug Commands

### 1. View Recent Logs
```bash
docker logs pythinker-backend-1 --tail 200
```

### 2. Check Monitoring Health
```bash
bash scripts/check_monitoring.sh
```

### 3. Search Logs by Session
```bash
docker logs pythinker-backend-1 | grep "SESSION_ID"
```

---

## 📊 Key Grafana Queries (LogQL)

### Find Session Errors
```logql
{container_name="pythinker-backend-1"}
|= "SESSION_ID"
|~ "error|ERROR|failed|stuck"
```

### View Tool Calls
```logql
{container_name="pythinker-backend-1"}
|= "SESSION_ID"
|~ "tool_started|tool_completed|tool_error"
```

### Check Stuck Patterns
```logql
{container_name="pythinker-backend-1"}
|~ "stuck|recovery|force-fail"
```

### View Step Execution
```logql
{container_name="pythinker-backend-1"}
|= "SESSION_ID"
|~ "Step.*started|Step.*completed|Step.*failed"
```

---

## 📈 Key Prometheus Queries (PromQL)

### Stuck Detection Rate
```promql
rate(pythinker_agent_stuck_detections_total[5m])
```

### Step Failure Rate
```promql
rate(pythinker_step_failures_total[5m])
```

### Tool Error Rate
```promql
pythinker_tool_errors_total
```

### Tool Performance (p95)
```promql
histogram_quantile(0.95, rate(pythinker_tool_call_duration_seconds_bucket[5m]))
```

### Compression Rejections
```promql
rate(pythinker_compression_rejected_total[5m])
```

### LLM Latency
```promql
histogram_quantile(0.95, rate(pythinker_llm_latency_seconds_bucket[5m]))
```

---

## 🎯 Debugging Workflow

**For ANY issue, follow this order:**

1. **Check Docker Logs First**
   ```bash
   docker logs pythinker-backend-1 --tail 200 | grep -i "error\|warning\|stuck"
   ```

2. **Open Grafana and Search Logs**
   - Go to: http://localhost:3001/explore
   - Select: Loki data source
   - Query by session_id or keywords

3. **Check Metrics in Prometheus**
   - Go to: http://localhost:9090/graph
   - Query relevant metrics (see above)

4. **View Dashboards for Trends**
   - Go to: http://localhost:3001/dashboards
   - Check "Pythinker Agent Monitoring"

5. **Correlate Logs + Metrics**
   - Use Grafana split view
   - Match timestamps between logs and metrics

---

## 🔧 Common Issues & Quick Checks

### Stuck Steps (0/5 tasks)
```bash
# Check logs
docker logs pythinker-backend-1 | grep "stuck\|recovery"

# Check Prometheus
# Query: pythinker_agent_stuck_detections_total
```

### Tool Errors
```bash
# Check which tool failed
docker logs pythinker-backend-1 | grep "tool_error"

# Check Prometheus
# Query: pythinker_tool_errors_total
```

### Validation Issues
```bash
# Check compression
docker logs pythinker-backend-1 | grep "compression"

# Check Prometheus
# Query: pythinker_compression_rejected_total
```

### Performance Issues
```bash
# Check LLM latency
# Prometheus Query: pythinker_llm_latency_seconds

# Check tool duration
# Prometheus Query: pythinker_tool_call_duration_seconds
```

---

## 💡 Pro Tips

1. **Always filter by session_id** to focus on specific issues

2. **Use time ranges** - Set Grafana to the exact time the issue occurred

3. **Check multiple sources**:
   - Logs show WHAT happened
   - Metrics show HOW OFTEN it happens
   - Dashboards show TRENDS

4. **Save useful queries** in Grafana for reuse

5. **Use regex in LogQL** to find patterns: `|~ "pattern1|pattern2"`

---

## 📚 Full Documentation

- **Complete Guide:** `docs/monitoring/MONITORING_STACK_GUIDE.md`
- **Setup Guide:** `MONITORING_SETUP_COMPLETE.md`
- **Scripts:** `scripts/check_monitoring.sh`, `scripts/monitor_session_logs.sh`

---

**Remember: The monitoring stack is your first stop for ALL debugging! 🔍**
