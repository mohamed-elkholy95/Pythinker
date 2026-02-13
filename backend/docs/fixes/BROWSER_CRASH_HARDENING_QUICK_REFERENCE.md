# Browser Crash Hardening - Quick Reference

## What Changed?

### 🔧 Configuration (No Action Required)
New settings with sensible defaults - no environment changes needed:
- `BROWSER_CRASH_CIRCUIT_BREAKER_ENABLED=true` (default)
- `BROWSER_CRASH_THRESHOLD=3` (default)
- `BROWSER_CRASH_WINDOW_SECONDS=300` (5 min, default)
- `BROWSER_QUICK_HEALTH_CHECK_ENABLED=true` (default)

### ⚡ Performance Improvements
- **Crash Detection**: 120s → <5s (96% faster)
- **Pre-operation Check**: None → 3s (proactive)
- **Circuit Breaker**: Prevents infinite retry loops
- **Pool Cleanup**: Background → Immediate (real-time)

### 📝 Log Messages to Watch

**Circuit Breaker Opened:**
```
Circuit breaker OPEN: 3 crashes in 300.0s window. Cooldown: 60s
```
**Action**: Browser had 3+ crashes in 5 minutes. System will wait 60s before allowing new operations.

**Recovery in Progress:**
```
Browser crashed, recovering... (attempt 2/3, retrying in 2.0s)
```
**Action**: Automatic recovery in progress. No user action needed.

**Crash Recorded:**
```
Browser crash recorded: 2 crashes in last 300.0s (threshold: 3)
```
**Action**: Tracking crashes. If count reaches 3, circuit breaker will open.

## Troubleshooting

### Too Many Circuit Breaker Openings?

**Symptoms:**
- Frequent "Circuit breaker OPEN" messages
- Browser operations failing with `BrowserCrashedError`

**Solutions:**
1. **Increase threshold** - Allow more crashes before opening:
   ```env
   BROWSER_CRASH_THRESHOLD=5
   ```

2. **Increase window** - Track crashes over longer period:
   ```env
   BROWSER_CRASH_WINDOW_SECONDS=600  # 10 minutes
   ```

3. **Check sandbox health** - Underlying infrastructure issue:
   ```bash
   docker logs pythinker-sandbox-1 --tail 200
   ```

### Circuit Breaker Never Opens?

**Symptoms:**
- Browser keeps crashing with no circuit protection
- Crashes but no "Circuit breaker OPEN" messages

**Check:**
1. Circuit breaker enabled?
   ```bash
   docker exec pythinker-backend-1 env | grep BROWSER_CRASH
   ```

2. Threshold too high?
   ```env
   BROWSER_CRASH_THRESHOLD=3  # Lower this
   ```

### Health Checks Too Aggressive?

**Symptoms:**
- Frequent "Browser unhealthy before navigation" warnings
- Operations slow due to health checks

**Solutions:**
1. **Increase timeout**:
   ```env
   BROWSER_QUICK_HEALTH_CHECK_TIMEOUT=5.0  # Up from 3s
   ```

2. **Disable quick health checks** (not recommended):
   ```env
   BROWSER_QUICK_HEALTH_CHECK_ENABLED=false
   ```

## Monitoring Queries

### Grafana/Loki Queries

**Circuit breaker activity:**
```logql
{container_name="pythinker-backend-1"} |= "Circuit breaker"
```

**Crash rate (last 5 min):**
```logql
rate({container_name="pythinker-backend-1"} |= "Browser crash recorded"[5m])
```

**Recovery attempts:**
```logql
{container_name="pythinker-backend-1"} |= "Browser crashed, recovering"
```

### Docker Logs

**Recent circuit breaker events:**
```bash
docker logs pythinker-backend-1 --tail 500 | grep "Circuit breaker"
```

**Crash recovery timeline:**
```bash
docker logs pythinker-backend-1 --tail 500 | grep -E "(crash|recovering)"
```

## Configuration Profiles

### Development (Lenient)
```env
# More forgiving for local development
BROWSER_CRASH_THRESHOLD=5
BROWSER_CRASH_WINDOW_SECONDS=600
BROWSER_CRASH_COOLDOWN_SECONDS=30
```

### Production (Balanced)
```env
# Default values - good for production
BROWSER_CRASH_THRESHOLD=3
BROWSER_CRASH_WINDOW_SECONDS=300
BROWSER_CRASH_COOLDOWN_SECONDS=60
```

### Strict (High Stability)
```env
# Fail fast for maximum stability
BROWSER_CRASH_THRESHOLD=2
BROWSER_CRASH_WINDOW_SECONDS=180
BROWSER_CRASH_COOLDOWN_SECONDS=120
```

### Debug (Disabled)
```env
# Disable for debugging browser issues
BROWSER_CRASH_CIRCUIT_BREAKER_ENABLED=false
BROWSER_QUICK_HEALTH_CHECK_ENABLED=false
```

## Code Examples

### Check Circuit State
```python
from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

browser = PlaywrightBrowser()
if browser._check_circuit_breaker():
    print("Circuit closed - operations allowed")
else:
    print("Circuit open - too many crashes")
```

### Manual Crash Recording
```python
# Record a crash for tracking
browser._record_crash()
print(f"Crashes in window: {len(browser._crash_history)}")
```

### Health Check Before Operation
```python
is_healthy = await browser._quick_health_check()
if not is_healthy:
    print("Browser unhealthy - will reinitialize")
```

## Migration Notes

### Backward Compatibility
- ✅ No breaking changes
- ✅ All features use default values
- ✅ Existing code works unchanged
- ✅ Can be disabled via config

### New Error Types
- `BrowserCrashedError` with `circuit_breaker_open` reason
- Enhanced error context with operation info

### Testing
```bash
# Run crash hardening tests
pytest tests/infrastructure/external/browser/test_crash_hardening.py -v

# Test circuit breaker
python -c "from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser; b = PlaywrightBrowser(); print('OK')"
```

## Quick Wins

1. **Faster Crash Detection** - Crashes detected in <5s vs 120s+
2. **No Infinite Loops** - Circuit breaker prevents retry storms
3. **Better Logging** - Recovery progress visible in logs
4. **Pool Stability** - Crashed connections removed immediately
5. **Zero Config** - Works out of the box with defaults

## Support

### Get Help
- Review logs: `docker logs pythinker-backend-1 --tail 500`
- Check configuration: `docker exec pythinker-backend-1 env | grep BROWSER`
- Run tests: `pytest tests/infrastructure/external/browser/test_crash_hardening.py`

### Report Issues
Include in bug reports:
- Circuit breaker log messages
- Crash history (count and timing)
- Configuration values
- Sandbox health status

## Related Docs
- Full implementation: `BROWSER_CRASH_HARDENING.md`
- Summary: `BROWSER_CRASH_HARDENING_SUMMARY.md`
- SSE timeout issues: `SSE_TIMEOUT_AND_UX_BUGS.md`
