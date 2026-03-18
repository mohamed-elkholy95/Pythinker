# Load Testing

Locust-based load testing for Pythinker API.

## Setup

```bash
pip install locust
```

## Usage

### Web UI Mode (Interactive)

```bash
cd backend
locust -f tests/load/locustfile.py --host http://localhost:8000
```

Open http://localhost:8089 to configure users, spawn rate, and view real-time charts.

### Headless Mode (CI/Scripts)

```bash
locust -f tests/load/locustfile.py \
    --host http://localhost:8000 \
    --headless \
    --users 50 \
    --spawn-rate 5 \
    --run-time 5m \
    --csv results/load_test
```

### Test Scenarios

| Task | Weight | Description |
|------|--------|-------------|
| health_check | 5 | Health endpoint (load balancer probes) |
| send_chat_message | 4 | Chat message submission |
| get_session_events | 3 | Event pagination (validates $slice fix) |
| create_session | 3 | Session creation |
| list_sessions | 2 | Session listing |
| get_session_detail | 1 | Full session detail |
| generate_upload_url | 1 | Presigned upload URL |

### Recommended Test Plans

**Smoke test** (verify endpoints work): 5 users, 1/s spawn, 1 minute
**Load test** (normal traffic): 50 users, 5/s spawn, 5 minutes
**Stress test** (find breaking point): 200 users, 10/s spawn, 10 minutes
**Soak test** (memory leaks): 30 users, 3/s spawn, 1 hour

### Auth

Tests auto-authenticate using the local auth endpoint (`LOCAL_AUTH_PASSWORD`).
Set this in your `.env` or the test will run unauthenticated (some endpoints may 401).
