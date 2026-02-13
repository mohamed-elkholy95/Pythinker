# Browser Retry Progress Events

**Status**: ✅ Implemented
**Date**: 2026-02-12
**Related Issue**: SSE Timeout and UX Bugs (MEMORY.md)

## Problem

When browser connections fail and retry (e.g., during Chrome crashes), users see no feedback during the retry attempts. This creates a poor UX where the chat appears frozen while the system is actively working to recover.

**Example scenario:**
1. Chrome crashes during navigation
2. System detects crash and starts retry logic (3 attempts)
3. Each retry takes several seconds
4. User sees no feedback for 10-15 seconds
5. Either succeeds silently or fails with generic timeout

## Solution

Implemented progress event emission during browser connection retry attempts. Users now see real-time feedback like:

```
Retrying browser connection (attempt 1/3)...
Retrying browser connection (attempt 2/3)...
```

### Architecture

**Callback-Based Design** (DDD-compliant):

```
Application Layer (agent_service.py)
    ↓ creates callback with session_repository access
DockerSandbox
    ↓ passes callback to connection pool
BrowserConnectionPool
    ↓ passes callback to retry logic
_create_connection_with_retry()
    ↓ calls callback on each retry
MessageEvent emitted to session
```

### Key Components

#### 1. Connection Pool (`connection_pool.py`)

Added `ProgressCallback` type and optional `progress_callback` parameter:

```python
ProgressCallback = Callable[[str], Awaitable[None]]

async def _create_connection_with_retry(
    self,
    cdp_url: str,
    block_resources: bool,
    randomize_fingerprint: bool,
    error_context: BrowserErrorContext,
    max_retries: int = 1,
    progress_callback: ProgressCallback | None = None,
) -> PooledConnection:
    for attempt in range(max_retries):
        # Emit progress event on retry attempts (not first attempt)
        if attempt > 0 and progress_callback:
            try:
                await progress_callback(
                    f"Retrying browser connection (attempt {attempt + 1}/{max_retries})..."
                )
            except Exception as e:
                logger.warning(f"Failed to emit retry progress event: {e}")
```

**Design decisions:**
- Callback only called on retries (attempt > 0), not first attempt
- Exceptions in callback don't break retry logic (caught and logged)
- Clear user-friendly messages with attempt numbers
- No spam - one event per retry attempt only

#### 2. DockerSandbox (`docker_sandbox.py`)

Added progress callback setter and storage:

```python
def set_browser_progress_callback(
    self, callback: Callable[[str], Awaitable[None]] | None
) -> None:
    """Set callback for browser connection retry progress events."""
    self._browser_progress_callback = callback
```

Passes callback through to connection pool in `browser()` method:

```python
connection = await pool._acquire_connection(
    cdp_url=self.cdp_url,
    block_resources=block_resources,
    session_id=session_id,
    sandbox_id=self.id,
    progress_callback=self._browser_progress_callback,  # ← Pass through
)
```

#### 3. AgentService (`agent_service.py`)

Creates callback with access to session repository:

```python
if hasattr(sandbox, "set_browser_progress_callback"):
    async def browser_progress_callback(message: str) -> None:
        """Emit browser connection retry progress as MessageEvent."""
        from app.domain.models.event import MessageEvent

        try:
            event = MessageEvent(
                session_id=session_id,
                role="assistant",
                message=message,
            )
            await self._session_repository.add_event(session_id, event)
            logger.debug(f"Emitted browser progress event: {message}")
        except Exception as e:
            logger.warning(f"Failed to emit browser progress event: {e}")

    sandbox.set_browser_progress_callback(browser_progress_callback)
```

**Why in AgentService?**
- Only place with access to both sandbox and session_repository
- Follows DDD layering (application orchestrates domain services)
- Clean separation of concerns

### Testing

Comprehensive test suite in `tests/infrastructure/test_browser_retry_progress.py`:

1. **test_retry_progress_callback_called_on_failure** - Verifies callback is called for each retry
2. **test_retry_progress_callback_not_called_on_success** - Verifies no spam when connection succeeds immediately
3. **test_retry_progress_callback_exception_doesnt_break_retry** - Ensures callback exceptions don't break retry logic
4. **test_retry_progress_callback_with_timeout_errors** - Tests timeout error scenarios
5. **test_set_browser_progress_callback** - Tests DockerSandbox setter
6. **test_clear_browser_progress_callback** - Tests clearing callback

### User Experience

**Before:**
```
[User]: Navigate to https://example.com
[System]: *silence for 15 seconds*
[System]: Navigation successful
```

**After:**
```
[User]: Navigate to https://example.com
[System]: Retrying browser connection (attempt 1/3)...
[System]: Retrying browser connection (attempt 2/3)...
[System]: Navigation successful
```

### Configuration

No configuration needed - automatically enabled when:
1. Browser connection retry logic is triggered
2. Sandbox has progress callback set (done automatically in AgentService)

### Performance Impact

- **Negligible** - Single event emission per retry attempt
- Callback is async and non-blocking
- Exceptions in callback don't affect retry logic
- No additional retries or delays introduced

### Edge Cases Handled

1. **Callback is None** - Skip event emission (graceful degradation)
2. **Callback raises exception** - Log warning, continue retry
3. **First attempt succeeds** - No events emitted (no spam)
4. **Session not found** - Event emission fails silently (logged)
5. **Multiple concurrent retries** - Each gets own callback context

### Future Enhancements

Potential improvements (not currently implemented):

1. **Granular progress** - Show retry delay countdown
   ```
   Retrying browser connection in 2 seconds... (attempt 1/3)
   Retrying browser connection in 1 second... (attempt 1/3)
   ```

2. **Retry reason** - Include why retry is needed
   ```
   Browser crashed, retrying connection (attempt 1/3)...
   Connection timeout, retrying (attempt 2/3)...
   ```

3. **Cancel retry** - Allow users to cancel retry attempts
   ```
   [Cancel Retry] button in UI
   ```

4. **Success notification** - Confirm when retry succeeds
   ```
   Browser connection restored successfully
   ```

### Related Files

- `backend/app/infrastructure/external/browser/connection_pool.py` - Progress callback implementation
- `backend/app/infrastructure/external/sandbox/docker_sandbox.py` - Callback setter and pass-through
- `backend/app/application/services/agent_service.py` - Callback creation with session repository
- `backend/app/domain/models/event.py` - MessageEvent model
- `backend/tests/infrastructure/test_browser_retry_progress.py` - Comprehensive test suite

### See Also

- `docs/fixes/SSE_TIMEOUT_AND_UX_BUGS.md` - Root cause analysis
- `docs/fixes/SSE_TIMEOUT_QUICK_REFERENCE.md` - Quick reference
- `MEMORY.md` - Known critical issues
