# Sandbox Container Fix Report

**Generated:** 2026-01-27
**Status:** FIXED - Container healthy

## Executive Summary

**RESOLVED**: Container is now healthy with lazy-loaded PostgreSQL.

### Fixes Applied

1. **Lazy PostgreSQL Loading** (`sandbox/app/framework/db.py`)
   - PostgreSQL now starts on-demand when first DB operation is requested
   - Framework service starts immediately without waiting for DB
   - DB is initialized lazily via `ensure_db_ready()` function

2. **PostgreSQL Socket Directory** (`sandbox/scripts/start-postgres.sh`)
   - Changed socket directory from `/var/run/postgresql` to `/tmp/pgsocket`
   - Postgres user has write access to `/tmp`

3. **Supervisord Configuration** (`sandbox/supervisord.conf`)
   - PostgreSQL `autostart=false` - starts only when needed
   - Removed postgres from mandatory services group

4. **Retry Parameters** (`sandbox/app/framework/db.py`)
   - Increased max_retries from 30 to 60
   - Increased retry_delay from 0.5s to 1.0s

---

## Original Issue Analysis

The sandbox container was failing to become healthy because the **framework** FastAPI service could not connect to PostgreSQL. PostgreSQL failed to start due to a missing runtime directory.

---

## Issue #1: PostgreSQL Cannot Start (CRITICAL)

### Symptoms
```
Framework DB init failed (attempt 1-30/30): [Errno 111] Connect call failed ('127.0.0.1', 5432)
ERROR: Application startup failed. Exiting.
```

### Root Cause
PostgreSQL fails with:
```
FATAL: could not create lock file "/var/run/postgresql/.s.PGSQL.5432.lock": No such file or directory
```

The `/var/run/postgresql` directory doesn't exist because:
1. `/run` is mounted as tmpfs in docker-compose.yml (line 82)
2. tmpfs mounts are empty on container start
3. The `start-postgres.sh` script doesn't create the required directory

### Fix Required

**File:** `sandbox/scripts/start-postgres.sh`

Add directory creation at the beginning of the script:
```bash
# Create PostgreSQL run directory (required for socket/lock files)
mkdir -p /var/run/postgresql
chown postgres:postgres /var/run/postgresql
chmod 775 /var/run/postgresql
```

**Alternative Fix (Dockerfile):**

Add to `sandbox/Dockerfile` before the CMD:
```dockerfile
# Ensure PostgreSQL run directory exists with proper permissions
RUN mkdir -p /var/run/postgresql && \
    chown postgres:postgres /var/run/postgresql && \
    chmod 775 /var/run/postgresql
```

However, since `/run` is tmpfs, the Dockerfile fix alone won't work. The script fix is required.

---

## Issue #2: Supervisord Priority/Dependency Issue (MODERATE)

### Problem
The `framework` service (priority 55) starts before PostgreSQL (priority 5) is ready. Despite PostgreSQL having lower priority, the async startup means framework attempts DB connection before postgres is listening.

### Current Retry Behavior
- Framework retries 30 times with 0.5s delay (15 seconds total)
- PostgreSQL takes longer to initialize than 15 seconds

### Fix Options

**Option A:** Increase retry parameters in `sandbox/app/framework/db.py`:
```python
async def init_db() -> None:
    max_retries = 60  # Increase from 30
    retry_delay = 1.0  # Increase from 0.5
```

**Option B:** Add PostgreSQL readiness check in `start-postgres.sh`:
```bash
# After starting postgres, only exit after it's ready
until "$PG_BIN/pg_isready" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; do
  sleep 0.2
done
# Signal readiness
touch /tmp/postgres-ready
```

Then in supervisord.conf, add a dependency:
```ini
[program:framework]
...
depends_on=postgres
```

---

## Issue #3: Chrome/GCM Deprecated Endpoint Warnings (LOW)

### Symptoms
```
[ERROR:google_apis/gcm/engine/registration_request.cc:291] Registration response error message: DEPRECATED_ENDPOINT
[ERROR:google_apis/gcm/engine/mcs_client.cc:700] Error code: 401 Error message: Authentication Failed: wrong_secret
```

### Analysis
These are Chrome's Google Cloud Messaging (push notification) errors. They're harmless for the sandbox use case and don't affect browser functionality.

### Fix (Optional)
Add `--disable-background-networking` to CHROME_ARGS if not already present. This is already included but GCM may still attempt initialization.

No action required - these are cosmetic errors.

---

## Issue #4: IPv6 Binding Warning (LOW)

### Symptoms
```
listen6: bind: Address already in use
Not listening on IPv6 interface.
```

### Analysis
x11vnc fails to bind to IPv6 because another service may have bound to the same port. VNC still works on IPv4.

### Fix (Optional)
Add `-rfbport 5900 -no6` to x11vnc command to explicitly disable IPv6.

No action required - VNC works on IPv4.

---

## Issue #5: DBus Errors in Chrome (LOW)

### Symptoms
```
[ERROR:dbus/object_proxy.cc:573] Failed to call method: org.freedesktop.DBus.NameHasOwner
```

### Analysis
Chrome's DBus integration fails because the container doesn't run a DBus daemon. This doesn't affect browser automation.

### Fix (Optional)
Install and configure dbus, or add `--disable-dbus` to Chrome args.

No action required - browser automation works without DBus.

---

## Recommended Fix Implementation Order

### Phase 1: Critical (Immediate)

1. **Fix `sandbox/scripts/start-postgres.sh`:**

```bash
#!/usr/bin/env bash
set -euo pipefail

PGDATA="${PGDATA:-/tmp/pgdata}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-pythinker_sandbox}"
PG_BIN="$(pg_config --bindir)"

# CRITICAL: Create PostgreSQL run directory for socket/lock files
mkdir -p /var/run/postgresql
chown postgres:postgres /var/run/postgresql
chmod 775 /var/run/postgresql

mkdir -p "$PGDATA"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  "$PG_BIN/initdb" -D "$PGDATA" --username="$PGUSER" --no-locale
  {
    echo "listen_addresses='${PGHOST}'"
    echo "port=${PGPORT}"
  } >> "$PGDATA/postgresql.conf"
  {
    echo "local all all trust"
    echo "host all all 127.0.0.1/32 trust"
  } >> "$PGDATA/pg_hba.conf"
fi

"$PG_BIN/postgres" -D "$PGDATA" -c listen_addresses="$PGHOST" -p "$PGPORT" &
pg_pid=$!

until "$PG_BIN/pg_isready" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; do
  sleep 0.2
done

if ! "$PG_BIN/psql" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
  -tc "SELECT 1 FROM pg_database WHERE datname='${PGDATABASE}'" | grep -q 1; then
  "$PG_BIN/psql" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
    -c "CREATE DATABASE ${PGDATABASE};"
fi

wait "$pg_pid"
```

### Phase 2: Reliability (Optional)

2. **Increase retry timeout in `sandbox/app/framework/db.py`:**
```python
max_retries = 60
retry_delay = 1.0
```

---

## Verification Steps

After applying fixes:

1. Rebuild sandbox container:
   ```bash
   docker compose build sandbox
   docker compose up -d sandbox
   ```

2. Verify PostgreSQL starts:
   ```bash
   docker exec pythinker-sandbox-1 netstat -tlnp | grep 5432
   ```

3. Verify framework is healthy:
   ```bash
   docker exec pythinker-sandbox-1 curl -s http://localhost:8082/health
   ```

4. Check container health:
   ```bash
   docker ps --filter "name=sandbox" --format "{{.Status}}"
   # Expected: Up X minutes (healthy)
   ```

---

## Summary

| Issue | Severity | Fix Required | Status |
|-------|----------|--------------|--------|
| PostgreSQL runtime dir missing | CRITICAL | Yes | Blocking |
| Framework retry timeout | MODERATE | Recommended | Not blocking |
| Chrome GCM errors | LOW | No | Cosmetic |
| IPv6 binding warning | LOW | No | Cosmetic |
| DBus errors | LOW | No | Cosmetic |

**Primary fix:** Add `mkdir -p /var/run/postgresql && chown postgres:postgres /var/run/postgresql` to `start-postgres.sh`
