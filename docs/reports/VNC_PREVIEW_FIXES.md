# VNC Preview & Timeline Replay Fixes

**Date**: 2026-02-11
**Status**: 🔴 Issues Identified, Awaiting Implementation
**Priority**: P0 - High User Impact

---

## Executive Summary

| Issue | Severity | Impact | Priority |
|-------|----------|--------|----------|
| VNC Mini Preview not showing at session end | **HIGH** | Users can't see final desktop state | P0 |
| SESSION_END screenshot not captured | **HIGH** | Missing final state for replay | P0 |
| Timeline scrubber lacks tool context | **MEDIUM** | Screenshots without metadata | P1 |
| VNC shows generic state instead of final screenshot | **MEDIUM** | Poor UX at session completion | P1 |
| WebSocket reconnection missing jitter | **LOW** | Potential thundering herd | P2 |

---

## Issue #1: VNC Mini Preview Not Showing at Session End

### Problem Description

When a session completes, the VNC mini preview shows a generic "Initializing" state instead of the final desktop view.

### Root Cause

**File**: `frontend/src/components/VncMiniPreview.vue` (lines 235-246)

```typescript
const shouldShowLiveVnc = computed(() => {
  if (!props.sessionId || !props.enabled || props.isInitializing) {
    return false;
  }

  // BUG: This condition requires active tool context
  // When session ends, there's no active tool, so VNC never shows
  if (!effectiveToolContent.value) {
    return false;
  }

  return props.isActive || currentViewType.value === 'vnc';
});
```

**Flow when session ends**:
1. `isActive` → `false`
2. `toolContent` → cleared
3. `effectiveToolContent.value` → `undefined`
4. `shouldShowLiveVnc` → `false`
5. Falls back to generic tool-preview state

### Fix Implementation

**File**: `frontend/src/components/VncMiniPreview.vue`

```vue
<script setup lang="ts">
// ... existing code ...

const shouldShowLiveVnc = computed(() => {
  if (!props.sessionId || !props.enabled || props.isInitializing) {
    return false;
  }

  // Show VNC when:
  // 1. Tool is actively running OR
  // 2. Current view type is VNC (explicitly requested) OR
  // 3. Session exists but no active tool (session end/idle state)
  const hasActiveTool = props.isActive || currentViewType.value === 'vnc';
  const hasSessionIdle = props.sessionId && !props.isActive && !props.toolName;
  
  return hasActiveTool || hasSessionIdle;
});
</script>
```

### Testing

```typescript
// Test cases for shouldShowLiveVnc
describe('shouldShowLiveVnc', () => {
  it('returns true when tool is active', () => {
    wrapper.setProps({ sessionId: '123', isActive: true });
    expect(wrapper.vm.shouldShowLiveVnc).toBe(true);
  });

  it('returns true when session idle (session end)', () => {
    wrapper.setProps({ sessionId: '123', isActive: false, toolName: '' });
    expect(wrapper.vm.shouldShowLiveVnc).toBe(true);
  });

  it('returns false when initializing', () => {
    wrapper.setProps({ sessionId: '123', isInitializing: true });
    expect(wrapper.vm.shouldShowLiveVnc).toBe(false);
  });
});
```

---

## Issue #2: SESSION_END Screenshot Not Captured

### Problem Description

Final screenshot with trigger `SESSION_END` is not being captured, even though the code exists.

### Evidence

```
Session 73c2f38741bd4e3c analysis:
Total screenshots: 78
- Periodic: 72 (93%)
- Tool (before/after): 6 (7%)
- SESSION_END: 0 (0%) ← MISSING
```

### Root Cause

**File**: `backend/app/domain/services/agent_task_runner.py`

```python
# Current code - issues:
# 1. Exception logged at DEBUG level (invisible)
# 2. May execute after sandbox destroyed
# 3. No success verification
try:
    await self._screenshot_service.capture(ScreenshotTrigger.SESSION_END)
except Exception as e:
    logger.debug(f"Screenshot cleanup failed (non-critical): {e}")
```

### Fix Implementation

**File**: `backend/app/domain/services/agent_task_runner.py`

```python
from app.domain.models.screenshot import ScreenshotTrigger
from app.infrastructure.observability.prometheus_metrics import (
    screenshot_session_end_total,
)

class AgentTaskRunner:
    def __init__(self, ...):
        # ... existing init ...
        self._last_tool_name: str | None = None
        self._last_function_name: str | None = None

    async def _execute_tool(self, tool_name: str, function_name: str, ...):
        # Track last tool for SESSION_END metadata
        self._last_tool_name = tool_name
        self._last_function_name = function_name
        # ... rest of execution ...

    async def _cleanup_session(self) -> None:
        """Session cleanup with guaranteed final screenshot."""
        
        # 1. Capture SESSION_END BEFORE stopping periodic captures
        screenshot_captured = False
        if self._screenshot_service:
            try:
                screenshot = await self._screenshot_service.capture(
                    trigger=ScreenshotTrigger.SESSION_END,
                    tool_name=self._last_tool_name,
                    function_name=self._last_function_name,
                )
                if screenshot:
                    screenshot_captured = True
                    logger.info(
                        "SESSION_END screenshot captured",
                        extra={
                            "session_id": self._session_id,
                            "screenshot_id": screenshot.id,
                        }
                    )
                else:
                    logger.warning(
                        "SESSION_END screenshot returned None",
                        extra={"session_id": self._session_id}
                    )
            except Exception as e:
                logger.warning(
                    f"SESSION_END screenshot failed: {e}",
                    extra={"session_id": self._session_id},
                    exc_info=True
                )
        
        # 2. Record metric
        screenshot_session_end_total.inc(
            {"status": "success" if screenshot_captured else "failed"}
        )
        
        # 3. Stop periodic captures
        if self._screenshot_service:
            await self._screenshot_service.stop_periodic()
        
        # ... rest of cleanup ...
```

**File**: `backend/app/infrastructure/observability/prometheus_metrics.py`

```python
# Add new metric
screenshot_session_end_total = Counter(
    name="pythinker_screenshot_session_end_total",
    documentation="Session end screenshot capture attempts by status",
    labelnames=["status"],
)
```

### Testing

```python
# tests/domain/services/test_session_end_screenshot.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.domain.models.screenshot import ScreenshotTrigger

@pytest.mark.asyncio
async def test_session_end_screenshot_captured():
    """Verify SESSION_END screenshot is captured during cleanup."""
    runner = AgentTaskRunner(...)
    runner._screenshot_service = MagicMock()
    runner._screenshot_service.capture = AsyncMock(return_value=MagicMock(id="test_id"))
    runner._last_tool_name = "browser"
    runner._last_function_name = "navigate"
    
    await runner._cleanup_session()
    
    runner._screenshot_service.capture.assert_called_once_with(
        trigger=ScreenshotTrigger.SESSION_END,
        tool_name="browser",
        function_name="navigate",
    )

@pytest.mark.asyncio
async def test_session_end_screenshot_failure_logged():
    """Verify SESSION_END screenshot failure is logged at WARNING level."""
    runner = AgentTaskRunner(...)
    runner._screenshot_service = MagicMock()
    runner._screenshot_service.capture = AsyncMock(side_effect=Exception("Sandbox gone"))
    
    with pytest.MonkeyPatch.context() as m:
        mock_logger = MagicMock()
        m.setattr("app.domain.services.agent_task_runner.logger", mock_logger)
        await runner._cleanup_session()
        
        # Should log WARNING, not DEBUG
        mock_logger.warning.assert_called()
```

---

## Issue #3: Timeline Scrubber Lacks Tool Context

### Problem Description

93% of screenshots (periodic captures) lack tool context metadata, making timeline navigation difficult.

### Evidence

```
Session 73c2f38741bd4e3c:
- Screenshots with tool_name: 6/78 (7%)
- Screenshots without tool_name: 72/78 (93%)
```

### Root Cause

**File**: `backend/app/application/services/screenshot_service.py`

```python
# Periodic loop doesn't include tool context
async def _periodic_loop() -> None:
    while True:
        await asyncio.sleep(capture_interval)
        await self.capture(ScreenshotTrigger.PERIODIC)  # No tool info!
```

### Fix Implementation

**File**: `backend/app/application/services/screenshot_service.py`

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class ToolExecutionContext:
    """Context for enriching periodic screenshots with tool metadata."""
    tool_name: str | None = None
    function_name: str | None = None
    tool_call_id: str | None = None
    action_type: str | None = None


class ScreenshotCaptureService:
    """Captures screenshots during session execution for later replay."""
    
    MAX_PERIODIC_FAILURES = 3

    def __init__(
        self,
        sandbox,
        session_id: str,
        repository: ScreenshotRepository | None = None,
        mongodb=None,
    ):
        # ... existing init ...
        self._tool_context: ToolExecutionContext | None = None

    def set_tool_context(
        self,
        tool_name: str | None = None,
        function_name: str | None = None,
        tool_call_id: str | None = None,
        action_type: str | None = None,
    ) -> None:
        """Set current tool context for periodic captures.
        
        Call this when a tool starts execution to enrich periodic
        screenshots with tool metadata.
        """
        self._tool_context = ToolExecutionContext(
            tool_name=tool_name,
            function_name=function_name,
            tool_call_id=tool_call_id,
            action_type=action_type,
        )
        logger.debug(
            f"Tool context set: {tool_name}/{function_name}",
            extra={"session_id": self._session_id}
        )

    def clear_tool_context(self) -> None:
        """Clear tool context when tool execution completes."""
        self._tool_context = None
        logger.debug(
            "Tool context cleared",
            extra={"session_id": self._session_id}
        )

    async def capture(
        self,
        trigger: ScreenshotTrigger,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        function_name: str | None = None,
        action_type: str | None = None,
    ) -> SessionScreenshot | None:
        """Capture a screenshot. Never raises -- returns None on failure."""
        
        # For periodic captures, use stored context if not provided
        if trigger == ScreenshotTrigger.PERIODIC and self._tool_context:
            tool_name = tool_name or self._tool_context.tool_name
            function_name = function_name or self._tool_context.function_name
            tool_call_id = tool_call_id or self._tool_context.tool_call_id
            action_type = action_type or self._tool_context.action_type
        
        # ... rest of capture logic unchanged ...
```

**File**: `backend/app/domain/services/agent_task_runner.py`

```python
async def _execute_tool(self, tool_name: str, tool_input: dict, ...):
    """Execute tool with screenshot context tracking."""
    
    # Set tool context for periodic screenshots
    if self._screenshot_service:
        self._screenshot_service.set_tool_context(
            tool_name=tool_name,
            function_name=tool_input.get("function"),
            tool_call_id=tool_call_id,
        )
    
    try:
        # Capture TOOL_BEFORE screenshot
        if self._screenshot_service:
            await self._screenshot_service.capture(
                ScreenshotTrigger.TOOL_BEFORE,
                tool_name=tool_name,
                function_name=tool_input.get("function"),
                tool_call_id=tool_call_id,
            )
        
        # Execute tool
        result = await tool.execute(...)
        
        # Capture TOOL_AFTER screenshot
        if self._screenshot_service:
            await self._screenshot_service.capture(
                ScreenshotTrigger.TOOL_AFTER,
                tool_name=tool_name,
                function_name=tool_input.get("function"),
                tool_call_id=tool_call_id,
            )
        
        return result
        
    finally:
        # Clear tool context
        if self._screenshot_service:
            self._screenshot_service.clear_tool_context()
```

### Testing

```python
# tests/application/services/test_screenshot_context.py
import pytest
from app.application.services.screenshot_service import ScreenshotCaptureService

@pytest.mark.asyncio
async def test_periodic_screenshot_uses_tool_context():
    """Verify periodic captures use stored tool context."""
    service = ScreenshotCaptureService(mock_sandbox, "session-123", mock_repo, mock_mongo)
    
    # Set context
    service.set_tool_context(
        tool_name="browser",
        function_name="navigate",
        tool_call_id="call-456",
    )
    
    # Capture periodic (no explicit tool info)
    await service.capture(ScreenshotTrigger.PERIODIC)
    
    # Verify saved screenshot has tool context
    saved = await mock_repo.find_by_session("session-123", limit=1, offset=0)
    assert saved[0].tool_name == "browser"
    assert saved[0].function_name == "navigate"
    assert saved[0].tool_call_id == "call-456"

@pytest.mark.asyncio
async def test_clear_tool_context():
    """Verify context is cleared properly."""
    service = ScreenshotCaptureService(...)
    
    service.set_tool_context(tool_name="browser")
    assert service._tool_context is not None
    
    service.clear_tool_context()
    assert service._tool_context is None
```

---

## Issue #4: VNC Shows Generic State Instead of Final Screenshot

### Problem Description

When session ends, VNC preview should show final screenshot thumbnail, not generic icon.

### Root Cause

**File**: `frontend/src/components/VncMiniPreview.vue`

No handling for "session complete but no active tool" state.

### Fix Implementation

**File**: `frontend/src/components/VncMiniPreview.vue`

```vue
<template>
  <div class="vnc-mini-preview" :class="sizeClass" @click="emit('click')">
    
    <!-- ... existing states (initializing, wide research, terminal, etc.) ... -->
    
    <!-- VNC view (active tool context) -->
    <div v-else-if="shouldShowLiveVnc" class="vnc-container">
      <LiveViewer
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="true"
        prefer="vnc"
      />
    </div>

    <!-- NEW: Final screenshot thumbnail (session complete) -->
    <div
      v-else-if="shouldShowFinalScreenshot"
      class="final-screenshot-preview"
    >
      <img
        v-if="finalScreenshotUrl"
        :src="finalScreenshotUrl"
        alt="Final session state"
        class="final-screenshot-image"
        @error="handleImageError"
      />
      <div v-else class="final-screenshot-placeholder">
        <Monitor class="placeholder-icon" />
        <span class="placeholder-text">Session Complete</span>
      </div>
      <div class="completion-badge">
        <Check class="badge-icon" />
        <span>Complete</span>
      </div>
    </div>

    <!-- Generic tool indicator (fallback) -->
    <div v-else class="tool-preview">
      <!-- ... existing fallback ... -->
    </div>

    <!-- Hover overlay -->
    <div class="hover-overlay">
      <Monitor class="hover-icon" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Monitor, Check } from 'lucide-vue-next';
import LiveViewer from '@/components/LiveViewer.vue';
import { apiClient } from '@/api/client';

const props = withDefaults(defineProps<{
  sessionId?: string;
  enabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
  toolName?: string;
  toolFunction?: string;
  isActive?: boolean;
  contentPreview?: string;
  filePath?: string;
  isInitializing?: boolean;
  searchResults?: Array<{...}>;
  searchQuery?: string;
  toolContent?: ToolContent;
  isSummaryStreaming?: boolean;
  // NEW PROPS
  isSessionComplete?: boolean;
  finalScreenshotUrl?: string;
}>(), {
  // ... existing defaults ...
  isSessionComplete: false,
  finalScreenshotUrl: '',
});

const emit = defineEmits<{
  click: [];
}>();

// ... existing code ...

// NEW: Determine if we should show final screenshot
const shouldShowFinalScreenshot = computed(() => {
  // Show final screenshot when:
  // 1. Session is marked complete
  // 2. Not initializing
  // 3. No active tool
  // 4. Not showing live VNC
  return (
    props.isSessionComplete &&
    !props.isInitializing &&
    !props.isActive &&
    !shouldShowLiveVnc.value
  );
});

// NEW: Auto-fetch final screenshot if not provided
const autoFinalScreenshotUrl = ref('');
const imageError = ref(false);

watch([() => props.sessionId, () => props.isSessionComplete], async ([sessionId, isComplete]) => {
  if (isComplete && sessionId && !props.finalScreenshotUrl) {
    try {
      const response = await apiClient.get(`/sessions/${sessionId}/screenshots`, {
        params: { limit: 1, offset: 0 }
      });
      const screenshots = response.data?.data?.screenshots || [];
      if (screenshots.length > 0) {
        autoFinalScreenshotUrl.value = `/api/v1/sessions/${sessionId}/screenshots/${screenshots[0].id}`;
      }
    } catch (e) {
      console.debug('Failed to fetch final screenshot:', e);
    }
  }
}, { immediate: true });

const finalScreenshotUrl = computed(() => {
  return props.finalScreenshotUrl || autoFinalScreenshotUrl.value;
});

const handleImageError = () => {
  imageError.value = true;
};
</script>

<style scoped>
/* ... existing styles ... */

/* NEW: Final screenshot preview */
.final-screenshot-preview {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bolt-elements-bg-depth-2);
  overflow: hidden;
}

.final-screenshot-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.final-screenshot-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--bolt-elements-textTertiary);
}

.placeholder-icon {
  width: 24px;
  height: 24px;
}

.placeholder-text {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.completion-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  background: var(--function-success);
  color: white;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.badge-icon {
  width: 10px;
  height: 10px;
}
</style>
```

### Testing

```typescript
// tests/components/VncMiniPreview.spec.ts
import { mount } from '@vue/test-utils';
import VncMiniPreview from '@/components/VncMiniPreview.vue';

describe('VncMiniPreview', () => {
  describe('shouldShowFinalScreenshot', () => {
    it('returns true when session complete and no active tool', () => {
      const wrapper = mount(VncMiniPreview, {
        props: {
          sessionId: 'test-123',
          isSessionComplete: true,
          isActive: false,
          isInitializing: false,
        }
      });
      expect(wrapper.vm.shouldShowFinalScreenshot).toBe(true);
    });

    it('returns false when session is active', () => {
      const wrapper = mount(VncMiniPreview, {
        props: {
          sessionId: 'test-123',
          isSessionComplete: true,
          isActive: true, // Still active
        }
      });
      expect(wrapper.vm.shouldShowFinalScreenshot).toBe(false);
    });
  });

  describe('final screenshot display', () => {
    it('displays final screenshot image when URL provided', () => {
      const wrapper = mount(VncMiniPreview, {
        props: {
          sessionId: 'test-123',
          isSessionComplete: true,
          finalScreenshotUrl: '/api/v1/sessions/test/screenshots/123',
        }
      });
      expect(wrapper.find('.final-screenshot-image').exists()).toBe(true);
    });

    it('displays placeholder when image fails to load', async () => {
      const wrapper = mount(VncMiniPreview, {
        props: {
          sessionId: 'test-123',
          isSessionComplete: true,
          finalScreenshotUrl: '/invalid-url',
        }
      });
      
      await wrapper.find('.final-screenshot-image').trigger('error');
      expect(wrapper.find('.final-screenshot-placeholder').exists()).toBe(true);
    });
  });
});
```

---

## Issue #5: WebSocket Reconnection Missing Jitter

### Problem Description

WebSocket reconnection uses exponential backoff without jitter, potentially causing thundering herd.

### Root Cause

**File**: `frontend/src/components/SandboxViewer.vue`

```typescript
// Current: No jitter
const delay = Math.min(1000 * Math.pow(2, connectionAttempts), 10000);
```

### Fix Implementation

**File**: `frontend/src/components/SandboxViewer.vue`

```typescript
// Configuration
const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 10000;
const JITTER_FACTOR = 0.3; // ±30% randomization

/**
 * Calculate reconnection delay with exponential backoff and jitter.
 * 
 * @param attempt - Current attempt number (0-indexed)
 * @returns Delay in milliseconds
 * 
 * @example
 * // Attempt 0: ~1000ms ± 30%
 * // Attempt 1: ~2000ms ± 30%
 * // Attempt 2: ~4000ms ± 30%
 * // Attempt 3: ~8000ms ± 30%
 * // Attempt 4+: ~10000ms ± 30% (capped)
 */
function calculateReconnectDelay(attempt: number): number {
  // Exponential backoff: base * 2^attempt
  const exponentialDelay = BASE_DELAY_MS * Math.pow(2, attempt);
  
  // Cap at maximum
  const cappedDelay = Math.min(exponentialDelay, MAX_DELAY_MS);
  
  // Add jitter: ±30% randomization
  // This prevents synchronized reconnection attempts (thundering herd)
  const jitterRange = cappedDelay * JITTER_FACTOR;
  const jitter = (Math.random() * 2 - 1) * jitterRange;
  
  // Ensure minimum delay
  return Math.max(BASE_DELAY_MS, Math.round(cappedDelay + jitter));
}

// Usage in ws.onclose handler
ws.onclose = (e) => {
  ws = null;
  stopStatsTracking();
  cleanupInput();

  if (intentionalClose) {
    return;
  }

  const closeReason = e.reason || `WebSocket closed (code ${e.code})`;
  emit('disconnected', closeReason);

  const shouldRetry = !NON_RETRYABLE_WS_CODES.has(e.code) &&
    !closeReason.toLowerCase().includes('session not found') &&
    !closeReason.toLowerCase().includes('sandbox not found');

  if (props.enabled && shouldRetry && connectionAttempts < MAX_RECONNECT_ATTEMPTS) {
    const delay = calculateReconnectDelay(connectionAttempts);
    connectionAttempts++;
    
    statusText.value = `Reconnecting in ${(delay / 1000).toFixed(1)}s...`;
    isLoading.value = true;

    logger.debug(`WebSocket reconnect scheduled`, {
      attempt: connectionAttempts,
      delay_ms: delay,
      reason: closeReason,
    });

    reconnectTimeout = window.setTimeout(() => {
      screencastWsUrl.value = null;
      initConnection();
    }, delay);
  } else {
    emit('error', closeReason);
  }
};
```

### Testing

```typescript
// tests/components/SandboxViewer.spec.ts
import { calculateReconnectDelay } from '@/components/SandboxViewer.vue';

describe('calculateReconnectDelay', () => {
  it('returns base delay for first attempt', () => {
    // Run multiple times to account for jitter
    const delays = Array.from({ length: 100 }, () => calculateReconnectDelay(0));
    const avgDelay = delays.reduce((a, b) => a + b, 0) / delays.length;
    
    // Average should be close to 1000ms
    expect(avgDelay).toBeGreaterThan(700);
    expect(avgDelay).toBeLessThan(1300);
  });

  it('caps delay at MAX_DELAY_MS', () => {
    const delays = Array.from({ length: 100 }, () => calculateReconnectDelay(10));
    
    // All delays should be <= MAX + jitter
    expect(Math.max(...delays)).toBeLessThanOrEqual(13000);
  });

  it('includes jitter (non-deterministic)', () => {
    const delays = new Set<number>();
    for (let i = 0; i < 10; i++) {
      delays.add(calculateReconnectDelay(2));
    }
    
    // Should have variation due to jitter
    expect(delays.size).toBeGreaterThan(1);
  });
});
```

---

## Implementation Checklist

### Phase 1: Critical Fixes (P0)

- [ ] **Fix VNC preview logic** (`VncMiniPreview.vue`)
  - [ ] Update `shouldShowLiveVnc` computed
  - [ ] Add unit tests
  - [ ] Manual test: verify VNC shows at session end

- [ ] **Fix SESSION_END screenshot** (`agent_task_runner.py`)
  - [ ] Add `_last_tool_name` / `_last_function_name` tracking
  - [ ] Elevate log level to WARNING
  - [ ] Add `screenshot_session_end_total` metric
  - [ ] Add integration test
  - [ ] Manual test: verify SESSION_END screenshot captured

### Phase 2: Enhancements (P1)

- [ ] **Add tool context to periodic screenshots** (`screenshot_service.py`)
  - [ ] Add `ToolExecutionContext` dataclass
  - [ ] Add `set_tool_context()` / `clear_tool_context()` methods
  - [ ] Update periodic capture to use context
  - [ ] Integrate in `agent_task_runner.py`
  - [ ] Add unit tests

- [ ] **Add final screenshot display** (`VncMiniPreview.vue`)
  - [ ] Add `isSessionComplete` / `finalScreenshotUrl` props
  - [ ] Add `shouldShowFinalScreenshot` computed
  - [ ] Add final screenshot template section
  - [ ] Add CSS styles
  - [ ] Add auto-fetch logic
  - [ ] Add unit tests

### Phase 3: Reliability (P2)

- [ ] **Add WebSocket jitter** (`SandboxViewer.vue`)
  - [ ] Add `calculateReconnectDelay()` function
  - [ ] Update `ws.onclose` handler
  - [ ] Add unit tests for jitter calculation

---

## Metrics to Track

After implementation, monitor these metrics:

```promql
# SESSION_END screenshot success rate
rate(pythinker_screenshot_session_end_total{status="success"}[5m])
/
rate(pythinker_screenshot_session_end_total[5m])

# Screenshots with tool context
sum(rate(pythinker_screenshot_captures_total{trigger!="periodic"}[5m]))
/
sum(rate(pythinker_screenshot_captures_total[5m]))

# WebSocket reconnection rate
rate(pythinker_websocket_reconnects_total[5m])
```

---

## Rollback Plan

If issues arise after deployment:

1. **VNC Preview**: Revert `shouldShowLiveVnc` to original logic
2. **SESSION_END**: Disable capture in `agent_task_runner.py`
3. **Tool Context**: Set `screenshot_tool_context_enabled=false` (add feature flag)
4. **Final Screenshot**: Set `isSessionComplete=false` always
5. **Jitter**: Remove jitter function, use simple exponential backoff

---

## References

- Vue 3 Composition API Best Practices: https://vuejs.org/guide/reusability/composables.html
- WebSocket Reconnection Strategies: https://dev.to/hexshift/robust-websocket-reconnection-strategies
- Session Replay Best Practices: https://openreplay.com/resources/session-replay-guide
- Prometheus Best Practices: https://prometheus.io/docs/practices/

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2026-02-11 | Agent Analysis | Initial issue identification and fix plans |
