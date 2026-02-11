# Session Monitoring Guide

## Active Monitoring Session Started: $(date)

### 1. Real-Time Docker Logs
```bash
# Backend logs (running in background)
docker logs pythinker-backend-1 --tail 200 --follow

# All services
docker-compose logs -f
```

### 2. Prometheus Metrics Queries
**Visit**: http://localhost:9090

**Key Queries**:
```promql
# Stuck detections rate (last 5 minutes)
rate(pythinker_agent_stuck_detections_total[5m])

# Tool errors total
pythinker_tool_errors_total

# Step failures total
pythinker_step_failures_total

# LLM request duration (p95)
histogram_quantile(0.95, rate(pythinker_llm_request_duration_seconds_bucket[5m]))

# Active sessions
pythinker_active_sessions

# Step execution time (p95)
histogram_quantile(0.95, rate(pythinker_step_duration_seconds_bucket[5m]))
```

### 3. Grafana Dashboards
**Visit**: http://localhost:3001 (admin/admin)

**Dashboards**:
- Pythinker Overview
- LLM Performance
- Tool Usage
- Session Analytics

### 4. Loki LogQL Queries
**Via Grafana Explore** (http://localhost:3001/explore)

```logql
# Find session errors
{container_name="pythinker-backend-1"} |= "SESSION_ID" |~ "error|stuck|failed"

# Tool execution issues
{container_name="pythinker-backend-1"} |= "tool" |~ "error|failed|timeout"

# Stuck detection logs
{container_name="pythinker-backend-1"} |= "stuck" | json

# LLM errors
{container_name="pythinker-backend-1"} |= "llm" |~ "error|rate_limit|timeout"

# Recent session events (last 1 hour)
{container_name="pythinker-backend-1"} |= "session_id" | json | line_format "{{.timestamp}} [{{.level}}] {{.message}}"
```

### 5. Quick Health Checks
```bash
# Check all containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep pythinker

# Check backend health
curl http://localhost:8000/health

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .job, health: .health}'

# Check recent metrics
curl -s http://localhost:9090/api/v1/query?query=pythinker_active_sessions | jq '.data.result'
```

### 6. Issue Detection Patterns

**Common Issues to Watch**:
- [ ] Stuck steps (check `pythinker_agent_stuck_detections_total`)
- [ ] Tool errors (check `pythinker_tool_errors_total`)
- [ ] LLM timeouts (check logs with `|= "llm" |~ "timeout"`)
- [ ] Validation failures (check `pythinker_step_failures_total`)
- [ ] Memory issues (check container stats)
- [ ] Session crashes (check logs for exceptions)

### 7. Session-Specific Monitoring

Once you start a session, replace `SESSION_ID` with the actual ID:

```bash
# Monitor specific session logs
docker logs pythinker-backend-1 --follow | grep "SESSION_ID"

# Grafana query for specific session
{container_name="pythinker-backend-1"} |= "SESSION_ID" | json
```

---

## Next Steps
1. Start your Pythinker session (frontend: http://localhost:5174)
2. Copy the session ID when it appears
3. Use the monitoring commands above to track the session
4. Document any issues found in this file
