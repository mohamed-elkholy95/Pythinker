# Orphaned Task Cleanup - Operations Guide

**Last Updated**: 2026-02-13
**Related Issue**: Critical Race Condition - Orphaned Background Tasks

---

## Overview

The Orphaned Task Cleanup Service detects and cleans up:
- ✅ Orphaned Redis streams (`task:input:*`, `task:output:*`)
- ✅ Zombie agent sessions (status=RUNNING but no activity)
- ✅ Stale session cancel events
- ✅ Abandoned sandbox containers (logged but not auto-deleted for safety)

**Safety**: All cleanup operations are idempotent and safe for concurrent execution.

---

## Deployment Options

### Option 1: APScheduler (Recommended for Production)

**Integrated with FastAPI lifespan**

#### Configuration

Add to `backend/app/core/config.py`:

```python
# Cleanup settings
cleanup_interval_minutes: int = 5  # Run every 5 minutes
orphaned_stream_age_seconds: int = 300  # 5 minutes
zombie_session_age_seconds: int = 900  # 15 minutes
stale_cancel_event_age_seconds: int = 600  # 10 minutes
```

#### Integration

Add to `backend/app/main.py`:

```python
from app.application.services.cleanup_scheduler import cleanup_scheduler_lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup ...

    # Start cleanup scheduler
    async with cleanup_scheduler_lifespan(redis_client) as cleanup_scheduler:
        logger.info("Cleanup scheduler started")
        yield {
            # ... existing context ...
            "cleanup_scheduler": cleanup_scheduler,
        }

    # Scheduler stops automatically on shutdown
    logger.info("Cleanup scheduler stopped")
```

#### Verification

```bash
# Check logs for cleanup runs
docker logs pythinker-backend-1 | grep "orphaned task cleanup"

# Expected output every 5 minutes:
# INFO: Starting orphaned task cleanup
# INFO: Orphaned task cleanup completed orphaned_redis_streams=2 zombie_sessions=0 ...
```

---

### Option 2: System Cron (Alternative for Lightweight Deployments)

**Good for**: Smaller deployments, debugging, manual control

#### Setup

1. **Test manually first**:

```bash
# Run cleanup once
docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service

# Expected output:
# Cleanup completed: {'orphaned_redis_streams': 2, 'zombie_sessions': 0, ...}
```

2. **Add to crontab**:

```bash
# Edit crontab
crontab -e

# Add this line (runs every 5 minutes)
*/5 * * * * docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service >> /var/log/pythinker/cleanup.log 2>&1
```

3. **Create log directory**:

```bash
sudo mkdir -p /var/log/pythinker
sudo chown $USER:$USER /var/log/pythinker
```

4. **Verify cron is running**:

```bash
# Check cron is enabled
systemctl status cron

# Check logs
tail -f /var/log/pythinker/cleanup.log
```

#### Log Rotation

Create `/etc/logrotate.d/pythinker-cleanup`:

```
/var/log/pythinker/cleanup.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $USER $USER
}
```

---

## Monitoring

### Prometheus Metrics

Access metrics at: `http://localhost:8000/metrics`

**Key Metrics**:

```promql
# Cleanup runs (success/error)
pythinker_orphaned_task_cleanup_runs_total

# Resources cleaned
pythinker_orphaned_redis_streams_cleaned_total
pythinker_zombie_sessions_cleaned_total

# Cleanup duration
pythinker_orphaned_task_cleanup_duration_seconds
```

### Grafana Dashboard

**Query Examples**:

```promql
# Cleanup success rate (last hour)
rate(pythinker_orphaned_task_cleanup_runs_total{status="success"}[1h]) /
rate(pythinker_orphaned_task_cleanup_runs_total[1h])

# Average cleanup duration
rate(pythinker_orphaned_task_cleanup_duration_seconds_sum[5m]) /
rate(pythinker_orphaned_task_cleanup_duration_seconds_count[5m])

# Orphaned streams cleaned per hour
rate(pythinker_orphaned_redis_streams_cleaned_total[1h]) * 3600
```

### Alerting Rules

**Prometheus alerts** (`prometheus/alerts.yml`):

```yaml
groups:
  - name: orphaned_tasks
    rules:
      # Alert if cleanup fails repeatedly
      - alert: OrphanedTaskCleanupFailing
        expr: |
          rate(pythinker_orphaned_task_cleanup_runs_total{status="error"}[15m]) > 0.5
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Orphaned task cleanup failing repeatedly"
          description: "Cleanup has failed {{ $value }} times in last 15 minutes"

      # Alert if many orphaned streams detected
      - alert: HighOrphanedStreamRate
        expr: |
          rate(pythinker_orphaned_redis_streams_cleaned_total[1h]) > 10
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "High rate of orphaned Redis streams"
          description: "{{ $value }} streams/hour being orphaned - investigate root cause"

      # Alert if zombie sessions accumulating
      - alert: ZombieSessionsAccumulating
        expr: |
          rate(pythinker_zombie_sessions_cleaned_total[1h]) > 5
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "Zombie sessions accumulating"
          description: "{{ $value }} zombie sessions/hour - check SSE cancellation logic"
```

---

## Troubleshooting

### Issue: Cleanup Not Running

**Check 1**: APScheduler started?

```bash
docker logs pythinker-backend-1 | grep "Cleanup scheduler started"
```

**Check 2**: Cron running?

```bash
# Check crontab
crontab -l

# Check syslog for cron execution
grep CRON /var/log/syslog | tail -20
```

**Check 3**: Redis connection?

```bash
# Test Redis connection
docker exec pythinker-backend-1 python -c "
from redis.asyncio import Redis
import asyncio
async def test():
    r = Redis.from_url('redis://redis:6379')
    await r.ping()
    print('Redis OK')
asyncio.run(test())
"
```

---

### Issue: Too Many Orphaned Streams

**Indicates**: SSE disconnects not properly cancelled

**Investigation**:

```bash
# Check Redis for orphaned streams
docker exec pythinker-redis-1 redis-cli KEYS "task:*" | wc -l

# If count > 100, investigate recent disconnects
docker logs pythinker-backend-1 --tail 1000 | grep "client_disconnected"
```

**Root Cause Analysis**:

1. Are fixes deployed?
   - Check `base.py` has cancellation checks (lines 893, 998, 567)
   - Check `session_routes.py` has immediate cancellation (line 798)

2. Are background tasks properly cancelled?
   - Check `agent_task_runner.py` destroy() has cleanup (line 1828)

3. Monitor Prometheus:
   ```promql
   # SSE disconnects without immediate cancellation
   rate(sse_stream_close_total{reason="client_disconnected"}[5m])
   ```

---

### Issue: Too Many Zombie Sessions

**Indicates**: Sessions stuck in RUNNING state

**Investigation**:

```bash
# Count zombie sessions in MongoDB
docker exec pythinker-mongodb-1 mongosh pythinker --quiet --eval '
db.sessions.count({
  status: "running",
  updated_at: {$lt: new Date(Date.now() - 15*60*1000)}
})
'
```

**Root Cause Analysis**:

1. Check session update logic:
   - Is `updated_at` being updated on events?
   - Are events being emitted during long operations?

2. Check heartbeat:
   ```promql
   # Heartbeat rate
   rate(sse_stream_heartbeat_total[5m])
   ```

3. Check for stuck agent tasks:
   ```bash
   # Check Redis for active tasks
   docker exec pythinker-redis-1 redis-cli KEYS "task:*" | xargs -I {} docker exec pythinker-redis-1 redis-cli XLEN {}
   ```

---

## Performance Tuning

### Cleanup Interval

**Current**: 5 minutes (default)

**Adjust based on load**:

- **High traffic** (>100 sessions/hour): 3 minutes
- **Low traffic** (<20 sessions/hour): 10 minutes
- **Development**: 1 minute (for testing)

**Configuration**:

```python
# In config.py
cleanup_interval_minutes: int = 3  # More frequent cleanup
```

### Age Thresholds

**Orphaned Streams**: 300 seconds (5 minutes)
- ✅ Safe default: Most sessions complete within 5 min
- ⚠️ If sessions run >5 min: Increase to 900 (15 min)

**Zombie Sessions**: 900 seconds (15 minutes)
- ✅ Safe default: Allows recovery from temporary issues
- ⚠️ If sessions run >15 min: Increase to 1800 (30 min)

**Configuration**:

```python
# In config.py
orphaned_stream_age_seconds: int = 900  # 15 minutes
zombie_session_age_seconds: int = 1800  # 30 minutes
```

---

## Testing

### Manual Test

```bash
# 1. Create test orphaned stream
docker exec pythinker-redis-1 redis-cli XADD task:input:test-orphan "*" field value

# 2. Wait 6 minutes (exceeds 5-minute threshold)
sleep 360

# 3. Run cleanup
docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service

# 4. Verify stream deleted
docker exec pythinker-redis-1 redis-cli EXISTS task:input:test-orphan
# Expected: 0 (deleted)
```

### Load Test

```bash
# Create 100 orphaned streams
for i in {1..100}; do
  docker exec pythinker-redis-1 redis-cli XADD task:input:load-test-$i "*" field value
done

# Run cleanup
time docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service

# Check metrics
docker exec pythinker-backend-1 curl -s http://localhost:8000/metrics | grep orphaned_redis_streams
```

---

## Integration with CI/CD

### Pre-Deployment Check

Add to `.github/workflows/deploy.yml`:

```yaml
- name: Verify cleanup service
  run: |
    docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service
    if [ $? -ne 0 ]; then
      echo "Cleanup service failed"
      exit 1
    fi
```

### Post-Deployment Smoke Test

```bash
#!/bin/bash
# scripts/test-cleanup.sh

echo "Testing orphaned task cleanup..."

# Run cleanup
docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service

# Check metrics endpoint
METRICS=$(curl -s http://localhost:8000/metrics | grep orphaned_task_cleanup_runs_total | grep 'status="success"')

if [ -z "$METRICS" ]; then
  echo "❌ Cleanup failed - no success metrics"
  exit 1
fi

echo "✅ Cleanup working"
```

---

## FAQ

**Q: Will cleanup delete active sessions?**
A: No. Cleanup only touches sessions with no activity for 15+ minutes AND status=RUNNING/PENDING.

**Q: What if cleanup fails?**
A: Cleanup is idempotent - next run will retry. Check logs and Prometheus metrics.

**Q: Can I run cleanup manually?**
A: Yes: `docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service`

**Q: Will cleanup impact performance?**
A: No. Cleanup uses Redis SCAN (non-blocking) and processes in batches. Typical duration: <1s.

**Q: How do I disable cleanup?**
A: Remove scheduler initialization from `main.py` or set `cleanup_interval_minutes: 0` in config.

---

## Related Documentation

- **Fix Implementation**: `ISSUES_DEEP_DIVE.md`
- **Browser Logs**: `browser_logs_summary.md`
- **SSE Timeout Issue**: `docs/fixes/SSE_TIMEOUT_AND_UX_BUGS.md`
- **Memory Management**: `.claude/projects/.../memory/MEMORY.md`

---

**Document Version**: 1.0
**Reviewed By**: Systematic Debugging Protocol
**Production Ready**: ✅ Yes
