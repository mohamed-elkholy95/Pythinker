# Frontend-Backend Connectivity Fixes

## Issues Fixed

### 1. **SSE Automatic Reconnection** ✅
**Problem:** When backend restarts or network interrupts occur, SSE connections fail permanently without retry.

**Solution:** Implemented exponential backoff reconnection in `frontend/src/api/client.ts`:
- Automatically retries up to 5 times
- Exponential backoff: 1s → 2s → 4s → 8s → 16s (max 30s)
- Jitter added to prevent thundering herd
- Clear console messages about reconnection status
- Respects manual abort signals

**Code Changes:**
```typescript
// Before: Single connection attempt, fails permanently
onerror(err) {
  console.error('EventSource error:', err);
  reject(error);
}

// After: Automatic retry with backoff
onerror(err) {
  if (!aborted && retryCount < maxRetries) {
    const delay = Math.min(baseDelay * 2^retryCount, 30000);
    setTimeout(() => reconnect(), delay);
  }
}
```

### 2. **Health Check Endpoint** ✅
**Problem:** No way for frontend to verify backend availability before establishing connections.

**Solution:** Added lightweight health check endpoints:
- `/api/v1/health` - Quick connectivity check (new)
- `/api/v1/monitoring/health` - Comprehensive system health (existing)

**Backend:** `backend/app/interfaces/api/health_routes.py`
```python
@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": "...", "service": "pythinker-backend"}
```

### 3. **CORS Configuration** ✅
**Problem:** Port 5174 not in default development CORS origins.

**Solution:** Updated `backend/app/core/config.py` to include all common dev ports:
```python
return [
    "http://localhost:5173",  # Vite default
    "http://localhost:5174",  # Pythinker frontend
    "http://localhost:3000",  # React/Next.js
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174"
]
```

### 4. **Frontend Health Monitoring** ✅
**Problem:** No reusable way to monitor backend connectivity across components.

**Solution:** Created `frontend/src/composables/useBackendHealth.ts`:
```typescript
const { isHealthy, checkHealth, startMonitoring } = useBackendHealth();

// Manual check
await checkHealth();

// Automatic monitoring (every 30s)
startMonitoring();

// Wait for backend during startup
await waitForHealthy();
```

## Testing the Fixes

### 1. Test SSE Reconnection
```bash
# Start system
./dev.sh up -d

# Access frontend: http://localhost:5174
# Start a chat session

# Restart backend (simulates failure)
docker restart pythinker-backend-1

# Observe: Browser console shows reconnection attempts
# Expected: Connection recovers automatically after 1-2 retries
```

### 2. Test Health Check
```bash
# Check health endpoint
curl http://localhost:8000/api/v1/health

# Expected response:
# {"status":"healthy","timestamp":"2026-01-28T...","service":"pythinker-backend"}
```

### 3. Test CORS
```bash
# From browser console (http://localhost:5174)
fetch('http://localhost:8000/api/v1/health')
  .then(r => r.json())
  .then(console.log)

# Expected: No CORS errors, returns health data
```

## Configuration

### Environment Variables

**Backend** (`.env`):
```bash
# CORS origins (already configured)
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174
```

**Frontend** (`docker-compose-development.yml`):
```yaml
frontend-dev:
  environment:
    - VITE_API_URL=http://localhost:8000  # Browser uses this
    - BACKEND_URL=http://backend:8000      # Vite proxy uses this
```

### How It Works

1. **Browser → Backend (Direct)**:
   - Browser at `http://localhost:5174` connects to `http://localhost:8000`
   - Works because backend port 8000 is exposed to host
   - CORS allows localhost:5174

2. **Frontend Container → Backend (Docker Network)**:
   - Vite dev server can proxy `/api` to `http://backend:8000`
   - Uses Docker service name resolution
   - Alternative for environments where direct connection isn't possible

## Usage Examples

### Example 1: Chat Page with Health Check
```typescript
import { useBackendHealth } from '@/composables/useBackendHealth';

const { isHealthy, checkHealth } = useBackendHealth();

const sendMessage = async (message: string) => {
  // Check backend health before sending
  if (!isHealthy()) {
    const recovered = await checkHealth();
    if (!recovered) {
      showError('Backend is unreachable. Please try again.');
      return;
    }
  }

  // Proceed with sending message
  await sendChatMessage(message);
};
```

### Example 2: App-Wide Connection Monitor
```typescript
// In App.vue or main layout
import { useBackendHealth } from '@/composables/useBackendHealth';

const { isHealthy, startMonitoring } = useBackendHealth();

onMounted(() => {
  startMonitoring(30000); // Check every 30 seconds
});

// Show banner when unhealthy
<div v-if="!isHealthy()" class="warning-banner">
  ⚠️ Connection to backend lost. Reconnecting...
</div>
```

## Monitoring & Debugging

### Browser Console Messages

**Normal Operation:**
```
SSE connection established to /api/v1/sessions/abc123/chat
```

**Network Failure:**
```
EventSource error: TypeError: network error
SSE connection error. Retrying in 1s... (attempt 1/5)
SSE connection error. Retrying in 2s... (attempt 2/5)
SSE connection established to /api/v1/sessions/abc123/chat
```

**Max Retries Reached:**
```
SSE max reconnection attempts reached. Please refresh the page.
```

### Backend Logs

**Health Check:**
```
INFO [app.main] [abc12345] GET /api/v1/health - 200 (2.34ms)
```

**SSE Connection:**
```
INFO [app.main] [def67890] POST /api/v1/sessions/123/chat - Client: 172.19.0.10
```

**CORS:**
```
INFO [app.main] CORS configured with origins: ['http://localhost:5173', 'http://localhost:5174', ...]
```

## Rollback Instructions

If issues occur, revert changes:

```bash
# Revert frontend client.ts
git checkout HEAD -- frontend/src/api/client.ts

# Remove new files
rm backend/app/interfaces/api/health_routes.py
rm frontend/src/composables/useBackendHealth.ts
rm CONNECTIVITY_FIX_SUMMARY.md

# Revert routes and config
git checkout HEAD -- backend/app/interfaces/api/routes.py
git checkout HEAD -- backend/app/core/config.py

# Restart services
./dev.sh restart backend frontend-dev
```

## Future Improvements

1. **UI Connection Indicator**: Add visual status in navbar showing connection state
2. **Metrics**: Track SSE reconnection rates and health check failures
3. **Adaptive Retry**: Adjust retry strategy based on error type (4xx vs 5xx vs network)
4. **Service Worker**: Consider using service worker for connection management
5. **WebSocket Alternative**: For critical operations, consider WebSocket with built-in reconnection

## Related Files

- `frontend/src/api/client.ts` - SSE reconnection logic
- `frontend/src/composables/useBackendHealth.ts` - Health monitoring composable
- `backend/app/interfaces/api/health_routes.py` - Health check endpoint
- `backend/app/interfaces/api/monitoring_routes.py` - Comprehensive health endpoint
- `backend/app/core/config.py` - CORS configuration
- `backend/app/main.py` - CORS middleware setup
- `docker-compose-development.yml` - Environment variable configuration
