# VNC Reconnection Progress Indicators - Design Document

**Date:** 2026-02-13
**Status:** Approved
**Implementation:** Phase 1 (Core) + Phase 2 (Tests)

---

## Problem Statement

Users experience VNC reconnection attempts lasting up to 5 minutes (30 attempts with exponential backoff) during browser crashes or network issues. The current UI shows only "Connecting..." with no indication of:
- Whether reconnection is actively happening
- How many attempts have been made
- How long the system will continue retrying

This creates a poor user experience where users cannot distinguish between a frozen system and active recovery.

---

## Goals

1. **Transparency**: Show users that reconnection is actively happening
2. **Progress**: Display current attempt count (X/30)
3. **Simplicity**: Minimal code changes, no architectural complexity
4. **Reliability**: No new failure modes or race conditions

---

## Design Overview

### Architecture

**Component Hierarchy:**
```
LiveViewer.vue (Parent)
  ├─ State: vncReconnectAttempts (reactive)
  └─ VNCViewer.vue (Child)
      ├─ Props: reconnectAttempt (NEW)
      └─ UI: LoadingState with dynamic statusText
```

**Data Flow:**
1. `LiveViewer.vue` tracks reconnection attempts in `vncReconnectAttempts.value`
2. Passes current attempt as `reconnectAttempt` prop to `VNCViewer.vue`
3. `VNCViewer.vue` watches prop and updates `statusText` reactively
4. `LoadingState` component displays updated text to user

---

## Implementation Details

### LiveViewer.vue Changes

**Add prop to VNCViewer:**
```vue
<VNCViewer
  v-else
  :key="`vnc-${sessionId}-${vncKey}`"
  :session-id="sessionId"
  :enabled="enabled"
  :view-only="viewOnly"
  :compact-loading="compactLoading"
  :reconnect-attempt="vncReconnectAttempts"  <!-- NEW -->
  @connected="handleVncConnected"
  @disconnected="handleVncDisconnected"
  @credentialsRequired="emit('credentialsRequired')"
/>
```

No logic changes needed - `vncReconnectAttempts` already tracked.

---

### VNCViewer.vue Changes

**1. Add prop:**
```typescript
const props = defineProps<{
  sessionId: string;
  enabled?: boolean;
  viewOnly?: boolean;
  compactLoading?: boolean;
  reconnectAttempt?: number;  // NEW
}>();
```

**2. Add watcher for statusText:**
```typescript
import { watch } from 'vue';

watch(
  () => props.reconnectAttempt,
  (attempt) => {
    if (attempt && attempt > 0) {
      statusText.value = `Reconnecting (attempt ${attempt}/30)...`;
    } else if (!rfb || rfb.disconnected) {
      statusText.value = 'Connecting...';
    }
  },
  { immediate: true }
);
```

**Note:** Keep existing `statusText.value = 'Connecting...'` in `initVNCConnection()`.

---

## User Experience

### Scenario 1: Normal Connection
1. User starts session → **"Connecting..."**
2. Connection succeeds → VNC screen appears
3. ✅ No change from current behavior

### Scenario 2: Single Reconnection
1. Connection drops → **"Reconnecting (attempt 1/30)..."**
2. Reconnection succeeds after 1s → VNC screen appears
3. ✅ Clear feedback that recovery happened

### Scenario 3: Browser Crash Recovery
1. Browser crashes → **"Reconnecting (attempt 1/30)..."** (1s delay)
2. Still failing → **"Reconnecting (attempt 2/30)..."** (2s delay)
3. Still failing → **"Reconnecting (attempt 3/30)..."** (4s delay)
4. Eventually recovers at attempt 12 → VNC screen appears
5. ✅ User sees active recovery, knows system isn't frozen

### Scenario 4: Max Attempts Reached
1. After 30 failed attempts → **"Reconnecting (attempt 30/30)..."**
2. System stops retrying (existing behavior)
3. ✅ User understands reconnection exhausted all attempts

---

## Error Handling

### Edge Cases Handled

| Case | Behavior |
|------|----------|
| Prop not provided | Defaults to `0`, shows "Connecting..." |
| Attempt count resets | Reactive prop updates statusText automatically |
| Component unmount during retry | Vue cleanup handles watchers |
| Session ID changes | New VNCViewer instance, attempt resets to 0 |
| Concurrent reconnections | `vncKey` changes prevent race conditions |

### No New Failure Modes

- ✅ Props are synchronous and reactive
- ✅ No async operations added
- ✅ No network calls
- ✅ No new state synchronization issues

---

## Testing Strategy

### Unit Tests (VNCViewer.vue)

**File:** `frontend/tests/components/VNCViewer.spec.ts`

```typescript
describe('VNCViewer reconnection progress', () => {
  it('shows "Connecting..." when reconnectAttempt is 0', () => {
    const wrapper = mount(VNCViewer, {
      props: { sessionId: 'test', reconnectAttempt: 0 }
    });
    expect(wrapper.text()).toContain('Connecting...');
  });

  it('shows attempt count when reconnectAttempt > 0', () => {
    const wrapper = mount(VNCViewer, {
      props: { sessionId: 'test', reconnectAttempt: 5 }
    });
    expect(wrapper.text()).toContain('Reconnecting (attempt 5/30)...');
  });

  it('updates when reconnectAttempt prop changes', async () => {
    const wrapper = mount(VNCViewer, {
      props: { sessionId: 'test', reconnectAttempt: 1 }
    });
    expect(wrapper.text()).toContain('attempt 1/30');

    await wrapper.setProps({ reconnectAttempt: 10 });
    expect(wrapper.text()).toContain('attempt 10/30');
  });

  it('resets to "Connecting..." when attempt goes to 0', async () => {
    const wrapper = mount(VNCViewer, {
      props: { sessionId: 'test', reconnectAttempt: 5 }
    });
    expect(wrapper.text()).toContain('attempt 5/30');

    await wrapper.setProps({ reconnectAttempt: 0 });
    expect(wrapper.text()).toContain('Connecting...');
  });
});
```

### Integration Tests (LiveViewer.vue)

**File:** `frontend/tests/components/LiveViewer.spec.ts`

```typescript
describe('LiveViewer reconnection flow', () => {
  it('passes reconnect attempt to VNCViewer', async () => {
    const wrapper = mount(LiveViewer, {
      props: { sessionId: 'test', prefer: 'vnc' }
    });

    const vncViewer = wrapper.findComponent(VNCViewer);
    expect(vncViewer.props('reconnectAttempt')).toBe(0);

    // Simulate disconnection
    vncViewer.vm.$emit('disconnected', 'test');
    await nextTick();

    // Should increment attempt
    expect(vncViewer.props('reconnectAttempt')).toBe(1);
  });

  it('resets attempt count on successful connection', async () => {
    const wrapper = mount(LiveViewer, {
      props: { sessionId: 'test', prefer: 'vnc' }
    });

    const vncViewer = wrapper.findComponent(VNCViewer);

    // Trigger multiple disconnections
    vncViewer.vm.$emit('disconnected');
    await nextTick();
    expect(vncViewer.props('reconnectAttempt')).toBe(1);

    // Successful connection should reset
    vncViewer.vm.$emit('connected');
    await nextTick();
    expect(vncViewer.props('reconnectAttempt')).toBe(0);
  });
});
```

### E2E Tests (Optional)

**File:** `frontend/tests/e2e/vnc-reconnection.spec.ts`

```typescript
test('shows progress during browser crash recovery', async ({ page }) => {
  // Start session with VNC
  await page.goto('/chat');
  await startNewSession(page);

  // Wait for VNC to connect
  await expect(page.locator('.vnc-screen')).toBeVisible();

  // Kill Chrome in sandbox (simulate crash)
  await killChromeInSandbox();

  // Should show reconnection progress
  await expect(page.locator('text=/Reconnecting \\(attempt \\d+\\/30\\).../')).toBeVisible();

  // Wait for recovery
  await expect(page.locator('.vnc-screen')).toBeVisible({ timeout: 60000 });
});
```

---

## Implementation Phases

### Phase 1: Core Functionality (This PR)
- ✅ Modify `LiveViewer.vue` - add `reconnectAttempt` prop
- ✅ Modify `VNCViewer.vue` - accept prop, add watcher
- ✅ Add unit tests for VNCViewer
- ✅ Manual testing with browser crash simulation

**Estimated Effort:** 1-2 hours
**Files Changed:** 2
**Lines Added:** ~20

### Phase 2: Extended Test Coverage (Follow-up PR)
- ✅ Add integration tests for LiveViewer
- ✅ Add E2E test for browser crash recovery
- ✅ Test on different browsers (Chrome, Firefox, Safari)

**Estimated Effort:** 2-3 hours
**Files Changed:** 2 (test files)
**Lines Added:** ~100

---

## Non-Goals (Explicitly Out of Scope)

**Not implementing:**
- ❌ Countdown timer to next retry (adds complexity, not essential)
- ❌ Reconnection reason detection (not reliably detectable)
- ❌ Cancel reconnection button (edge case, adds UI complexity)
- ❌ Configurable max attempts (already set to 30, good default)
- ❌ Audio/visual alerts on reconnection (would be annoying)

**Why:** Following YAGNI principle - implement minimum viable solution, iterate based on user feedback.

---

## Success Criteria

1. ✅ Users see "Reconnecting (attempt X/30)..." during reconnections
2. ✅ Text updates in real-time as attempts increment
3. ✅ No console errors or warnings
4. ✅ All unit tests pass
5. ✅ Manual testing confirms behavior in browser crash scenario
6. ✅ No performance degradation
7. ✅ Code follows Vue 3 Composition API + TypeScript standards

---

## Related Issues

- **SSE Timeout Issue:** `docs/fixes/SSE_TIMEOUT_AND_UX_BUGS.md`
- **VNC Stability Improvements:** Commit `ee2b58b` (websockify + reconnect limit increase)
- **Browser Crash Hardening:** `docs/research/BROWSER_CRASH_PREVENTION_APPLIED.md`

---

## Approval

**Design Status:** ✅ Approved
**Approved By:** User
**Approval Date:** 2026-02-13

---

**Next Steps:** Create implementation plan with `/writing-plans` skill
