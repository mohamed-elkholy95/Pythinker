# Response Lifecycle State Machine - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace independent UI state booleans with a unified response lifecycle state machine so suggestions only appear on actual task completion, not on SSE timeouts/errors, and add visual polish for state transitions.

**Architecture:** A single `responsePhase` ref replaces `isResponseSettled`, `isLoading`, `isThinking` as the source of truth. Backward-compatible computed properties preserve existing template bindings. Heartbeat events from the backend drive a "still working" visual indicator. Suggestions are gated exclusively by the `SETTLED` phase.

**Tech Stack:** Vue 3 (Composition API), TypeScript, CSS transitions

**Design Doc:** `docs/plans/2026-02-12-response-lifecycle-state-machine-design.md`

---

## Task 1: Add `responsePhase` State Machine to ChatPage

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue:413-508` (state definition + destructured refs)

**Step 1: Add the `ResponsePhase` type and `responsePhase` ref**

In `ChatPage.vue`, add the type definition before `createInitialState()` (around line 412):

```typescript
type ResponsePhase = 'idle' | 'connecting' | 'streaming' | 'completing' | 'settled' | 'timed_out' | 'error' | 'stopped'
```

Inside `createInitialState()`, add `responsePhase` and `receivedDoneEvent` and `lastHeartbeatAt` to the state object. Remove the standalone booleans that are now derived: `isLoading`, `isResponseSettled`, `isThinking`. Keep `isWaitingForReply` as it's orthogonal (agent waiting for user input, not a response lifecycle state).

Replace these lines in the initial state:
```typescript
// REMOVE these from createInitialState:
// isLoading: false,
// isResponseSettled: false,
// isThinking: false,

// ADD these to createInitialState:
responsePhase: 'idle' as ResponsePhase,
receivedDoneEvent: false,
lastHeartbeatAt: 0,
```

**Step 2: Add computed properties for backward compatibility**

After the `toRefs(state)` destructuring block (line 508), add computed properties:

```typescript
// Response lifecycle: derived from responsePhase
const isLoading = computed(() => ['connecting', 'streaming', 'completing'].includes(responsePhase.value))
const isThinking = computed(() => responsePhase.value === 'connecting')
const isResponseSettled = computed(() => responsePhase.value === 'settled')
const canShowSuggestions = computed(() =>
  responsePhase.value === 'settled' && suggestions.value.length > 0 && !isSummaryStreaming.value
)
```

Remove `isLoading`, `isResponseSettled`, `isThinking` from the `toRefs(state)` destructuring block (lines 466, 483, 485) since they are now computed.

**Step 3: Add a `transitionTo` helper function**

Add after the computed properties:

```typescript
/** Transition the response lifecycle to a new phase. Centralizes all state changes. */
const transitionTo = (phase: ResponsePhase) => {
  const prev = responsePhase.value
  responsePhase.value = phase

  // Auto-transition: COMPLETING → SETTLED after 300ms
  if (phase === 'completing') {
    setTimeout(() => {
      if (responsePhase.value === 'completing') {
        responsePhase.value = 'settled'
      }
    }, 300)
  }

  console.debug(`[ResponsePhase] ${prev} → ${phase}`)
}
```

**Step 4: Verify the file saves and TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -30`

Expected: May show errors because existing code still assigns to `isLoading.value` etc. These will be fixed in subsequent tasks.

**Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "feat(chat): add responsePhase state machine type and computed properties"
```

---

## Task 2: Replace Direct Boolean Assignments with `transitionTo()`

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue` (multiple locations)

This task replaces all direct assignments to `isLoading.value`, `isResponseSettled.value`, and `isThinking.value` with `transitionTo()` calls. Since these are now computed properties, direct assignment will fail.

**Step 1: Fix the `'done'` event handler (line 2065-2078)**

Replace:
```typescript
  } else if (event.event === 'done') {
    ensureCompletionSuggestions();
    markShortAssistantCompletion();
    isResponseSettled.value = true;
    isLoading.value = false;
    isThinking.value = false;
    isWaitingForReply.value = false;
    // Notify sidebar that session is no longer running
    if (sessionId.value) {
      emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
    }
    // Load screenshots for replay mode (seamless live → replay transition)
    sessionStatus.value = SessionStatus.COMPLETED;
    replay.loadScreenshots();
```

With:
```typescript
  } else if (event.event === 'done') {
    receivedDoneEvent.value = true;
    ensureCompletionSuggestions();
    markShortAssistantCompletion();
    isWaitingForReply.value = false;
    transitionTo('completing') // → auto-settles to 'settled' after 300ms
    // Notify sidebar that session is no longer running
    if (sessionId.value) {
      emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
    }
    // Load screenshots for replay mode (seamless live → replay transition)
    sessionStatus.value = SessionStatus.COMPLETED;
    replay.loadScreenshots();
```

**Step 2: Fix the `'wait'` event handler (line 2079-2084)**

Replace:
```typescript
  } else if (event.event === 'wait') {
    isResponseSettled.value = true;
    // Agent is waiting for user input - show waiting indicator
    isWaitingForReply.value = true;
    isLoading.value = false;
    isThinking.value = false;
```

With:
```typescript
  } else if (event.event === 'wait') {
    // Agent is waiting for user input - show waiting indicator
    isWaitingForReply.value = true;
    transitionTo('settled')
```

**Step 3: Fix the `'error'` event handler (line 2085-2087)**

Replace:
```typescript
  } else if (event.event === 'error') {
    isResponseSettled.value = true;
    handleErrorEvent(event.data as ErrorEventData);
```

With:
```typescript
  } else if (event.event === 'error') {
    transitionTo('error')
    handleErrorEvent(event.data as ErrorEventData);
```

**Step 4: Fix the `processEvent` initialization transition (line 2047-2050)**

After `updateLastEventTime()` (line 2053), add a transition from `connecting` to `streaming` on first real event:

```typescript
  // Update last event time for stale connection detection
  updateLastEventTime();

  // Transition to streaming on first real event
  if (responsePhase.value === 'connecting') {
    transitionTo('streaming')
  }
```

**Step 5: Fix `sendMessage()` reset block (lines 2240-2250)**

Replace:
```typescript
  suggestions.value = [];
  isResponseSettled.value = false;
  isLoading.value = true;
  isWaitingForReply.value = false;
```

With:
```typescript
  suggestions.value = [];
  receivedDoneEvent.value = false;
  isWaitingForReply.value = false;
  transitionTo('connecting')
```

**Step 6: Fix SSE `onOpen` callback (line 2268-2270)**

Replace:
```typescript
        onOpen: () => {
          isLoading.value = true;
        },
```

With:
```typescript
        onOpen: () => {
          // responsePhase already set to 'connecting' in sendMessage
          // onOpen confirms transport is established, no phase change needed
        },
```

**Step 7: Fix SSE `onClose` callback (lines 2277-2297)**

Replace the entire `onClose` callback:

```typescript
        onClose: () => {
          // Transport closed. Check if we received a 'done' event.
          if (!receivedDoneEvent.value && responsePhase.value !== 'settled' && responsePhase.value !== 'error' && responsePhase.value !== 'stopped') {
            // SSE closed without a done event — timeout or disconnect
            transitionTo('timed_out')
          }
          // Clean up streaming state regardless
          thinkingText.value = '';
          isThinkingStreaming.value = false;
          summaryStreamText.value = '';
          isSummaryStreaming.value = false;
          allowStandaloneSummaryOnNextAssistant.value = false;
          isInitializing.value = false;
          planningProgress.value = null;
          stopPlanningMessageCycle();
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
          // NO ensureCompletionSuggestions() here — suggestions only on 'done'
        },
```

**Step 8: Fix SSE `onError` callback (lines 2298-2320)**

Replace the entire `onError` callback:

```typescript
        onError: () => {
          if (responsePhase.value !== 'settled' && responsePhase.value !== 'stopped') {
            transitionTo('error')
          }
          // Clean up streaming state
          thinkingText.value = '';
          isThinkingStreaming.value = false;
          summaryStreamText.value = '';
          isSummaryStreaming.value = false;
          allowStandaloneSummaryOnNextAssistant.value = false;
          isInitializing.value = false;
          planningProgress.value = null;
          stopPlanningMessageCycle();
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
          // NO ensureCompletionSuggestions() here
          if (sessionId.value) {
            emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
          }
        },
```

**Step 9: Fix `handleStop()` (lines 2624-2662)**

Replace the state reset block (lines 2646-2662):

```typescript
  // Reset to stopped state
  transitionTo('stopped')
  isStale.value = false;
  isWaitingForReply.value = false;
  thinkingText.value = '';
  isThinkingStreaming.value = false;
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;
  allowStandaloneSummaryOnNextAssistant.value = false;
  isInitializing.value = false;
  planningProgress.value = null;
  stopPlanningMessageCycle();
  // NO ensureCompletionSuggestions() — user intentionally stopped
  sessionStatus.value = SessionStatus.COMPLETED;
```

**Step 10: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -40`

Expected: Clean compilation (or only unrelated warnings).

**Step 11: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "refactor(chat): replace direct state booleans with transitionTo() calls"
```

---

## Task 3: Update Template to Use `canShowSuggestions`

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue:173-184` (template section)

**Step 1: Replace the Suggestions and TaskCompletedFooter v-if conditions**

Replace (lines 173-184):
```html
          <!-- Task completed - green checkmark above suggestions when response is done -->
          <TaskCompletedFooter
            v-if="suggestions.length > 0 && isResponseSettled && !isLoading && !isThinking && !isSummaryStreaming"
            :showRating="false"
            class="mt-3 mb-1"
          />
          <!-- Suggestions - show in dedicated area after response is complete -->
          <Suggestions
            v-if="suggestions.length > 0 && isResponseSettled && !isLoading && !isThinking && !isSummaryStreaming"
            :suggestions="suggestions"
            @select="handleSuggestionSelect"
          />
```

With:
```html
          <!-- Task completed - green checkmark above suggestions when response is done -->
          <TaskCompletedFooter
            v-if="canShowSuggestions"
            :showRating="false"
            class="mt-3 mb-1"
          />
          <!-- Suggestions - show in dedicated area after response is settled -->
          <Suggestions
            v-if="canShowSuggestions"
            :suggestions="suggestions"
            @select="handleSuggestionSelect"
            class="suggestions-enter"
          />
```

**Step 2: Add the "connection interrupted" banner for TIMED_OUT state**

After the `isStale` notice block (around line 171), add:

```html
          <!-- Connection interrupted - SSE closed without completion -->
          <div
            v-if="responsePhase === 'timed_out'"
            class="timeout-notice flex items-center gap-3 px-4 py-3 mx-4 mb-2 rounded-xl border border-amber-200 dark:border-amber-800/40 bg-amber-50 dark:bg-amber-950/20 transition-all duration-300"
            role="status"
          >
            <div class="w-2.5 h-2.5 rounded-full bg-amber-400 dark:bg-amber-500 flex-shrink-0 animate-pulse" aria-hidden="true"></div>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-amber-800 dark:text-amber-300">
                {{ $t('Connection interrupted. The agent may still be working.') }}
              </span>
            </div>
            <button
              @click="handleRetryConnection"
              class="flex-shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
            >
              {{ $t('Retry') }}
            </button>
          </div>
```

**Step 3: Add the `handleRetryConnection` function**

Add in the script section (near `handleStop`):

```typescript
const handleRetryConnection = async () => {
  if (!sessionId.value) return;
  transitionTo('connecting')
  // Reuse existing sendMessage flow with empty message to reconnect
  // The SSE client will use lastEventId for resume
  try {
    cancelCurrentChat.value = await agentApi.chatWithSession(
      sessionId.value,
      '', // empty message — just reconnect
      lastEventId.value,
      [],
      [],
      undefined,
      {
        onOpen: () => {},
        onMessage: ({ event, data }) => {
          handleEvent({
            event: event as AgentSSEEvent['event'],
            data: data as AgentSSEEvent['data']
          });
        },
        onClose: () => {
          if (!receivedDoneEvent.value && responsePhase.value !== 'settled' && responsePhase.value !== 'error' && responsePhase.value !== 'stopped') {
            transitionTo('timed_out')
          }
          thinkingText.value = '';
          isThinkingStreaming.value = false;
          summaryStreamText.value = '';
          isSummaryStreaming.value = false;
          allowStandaloneSummaryOnNextAssistant.value = false;
          isInitializing.value = false;
          planningProgress.value = null;
          stopPlanningMessageCycle();
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
        },
        onError: () => {
          if (responsePhase.value !== 'settled' && responsePhase.value !== 'stopped') {
            transitionTo('error')
          }
          thinkingText.value = '';
          isThinkingStreaming.value = false;
          summaryStreamText.value = '';
          isSummaryStreaming.value = false;
          allowStandaloneSummaryOnNextAssistant.value = false;
          isInitializing.value = false;
          planningProgress.value = null;
          stopPlanningMessageCycle();
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
        },
      }
    );
  } catch {
    transitionTo('error')
  }
}
```

**Step 4: Verify template renders**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20`

**Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "feat(chat): gate suggestions behind canShowSuggestions, add timeout banner with retry"
```

---

## Task 4: Fix Suggestion Fallback to Skip Greetings

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue:1641-1694` (suggestion generation)

**Step 1: Add greeting detection to `buildCompletionFallbackSuggestions()`**

At the top of `buildCompletionFallbackSuggestions()` (line 1641), after extracting `assistantContext`, add a greeting check:

```typescript
const buildCompletionFallbackSuggestions = (): string[] => {
  let assistantContext = '';
  let latestUserMessage = '';

  for (let i = messages.value.length - 1; i >= 0; i--) {
    const message = messages.value[i];
    if (message.type === 'assistant') {
      if (!assistantContext) {
        assistantContext = (message.content as MessageContent).content || '';
      }
      continue;
    }
    if (message.type === 'report') {
      if (!assistantContext) {
        const reportContent = message.content as ReportContent;
        assistantContext = `${reportContent.title || ''} ${reportContent.content || ''}`;
      }
      continue;
    }
    if (message.type === 'user') {
      latestUserMessage = ((message.content as MessageContent).content || '').trim();
      break;
    }
  }

  // Skip suggestions for greeting/trivial responses
  const combined = `${latestUserMessage} ${assistantContext}`.trim().toLowerCase();
  if (combined.length < 80 && !assistantContext.includes('```') && !assistantContext.includes('#')) {
    const greetingPatterns = /^(hi|hello|hey|good\s*(morning|afternoon|evening)|thanks|thank\s*you|ok|sure|yes|no|bye|goodbye|welcome)\b/i;
    if (greetingPatterns.test(latestUserMessage.trim()) || greetingPatterns.test(assistantContext.trim())) {
      return []; // No suggestions for greetings
    }
  }

  // ... rest of existing logic unchanged
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -10`

**Step 3: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "fix(chat): skip fallback suggestions for greeting/trivial responses"
```

---

## Task 5: Integrate Heartbeat Visual Feedback

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue:1577-1581` (heartbeat handler)
- Modify: `frontend/src/pages/ChatPage.vue:882-928` (stale detection)
- Modify: `frontend/src/components/ui/LoadingIndicator.vue` (add heartbeat pulse)

**Step 1: Update heartbeat handler to track `lastHeartbeatAt`**

Replace the heartbeat handler in `handleProgressEvent` (lines 1577-1581):

```typescript
const handleProgressEvent = (progressData: ProgressEventData) => {
  // Heartbeat: update timestamp for liveness tracking
  if (progressData.phase === 'heartbeat') {
    lastHeartbeatAt.value = Date.now();
    return;
  }
```

**Step 2: Refine stale detection to use heartbeat awareness**

Replace the stale detection constants and `checkStaleConnection` (lines 882-928):

```typescript
// ===== Agent Connection Health Monitoring =====
const STALE_TIMEOUT_MS = 30000; // 30s without heartbeat = possibly unstable
const HEARTBEAT_LIVENESS_MS = 20000; // Expect heartbeat every ~15s, allow 20s grace
const STALE_CHECK_INTERVAL_MS = 5000; // Check every 5 seconds
let staleCheckInterval: ReturnType<typeof setInterval> | null = null;

// Track whether we're receiving heartbeats (backend alive)
const isReceivingHeartbeats = computed(() => {
  if (lastHeartbeatAt.value === 0) return false;
  return (Date.now() - lastHeartbeatAt.value) < HEARTBEAT_LIVENESS_MS;
})

// Update last event time when any event is received
const updateLastEventTime = () => {
  lastEventTime.value = Date.now();
  isStale.value = false;
};

// Check if connection appears stale
const checkStaleConnection = () => {
  if (!isLoading.value) {
    isStale.value = false;
    return;
  }

  const timeSinceLastEvent = Date.now() - lastEventTime.value;
  const timeSinceHeartbeat = lastHeartbeatAt.value > 0 ? Date.now() - lastHeartbeatAt.value : Infinity;

  // If heartbeats are arriving but no real events, we're alive but working
  // Only mark stale if BOTH real events AND heartbeats are missing
  if (timeSinceLastEvent > STALE_TIMEOUT_MS && timeSinceHeartbeat > STALE_TIMEOUT_MS && lastEventTime.value > 0) {
    isStale.value = true;
  }
};
```

Keep the existing `watch(isLoading, ...)` block as-is since `isLoading` is now a computed that derives from `responsePhase`.

**Step 3: Update LoadingIndicator to accept a `pulse` prop**

Modify `frontend/src/components/ui/LoadingIndicator.vue`:

```vue
<template>
  <div
    class="loading-indicator flex items-center gap-2 text-[var(--text-tertiary)] text-sm"
    :class="{ 'heartbeat-active': pulse }"
    role="status"
    aria-live="polite"
  >
    <span class="loading-dots flex gap-1 relative top-[2px]" aria-hidden="true">
      <span
        v-for="(_, index) in 3"
        :key="index"
        class="w-1.5 h-1.5 rounded-full animate-bounce-dot bg-[var(--icon-tertiary)]"
        :style="{ 'animation-delay': `${index * 150}ms` }"
      ></span>
    </span>
    <span v-if="text" class="loading-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
interface Props {
  text?: string
  pulse?: boolean
}

withDefaults(defineProps<Props>(), {
  text: undefined,
  pulse: false,
})
</script>

<style scoped>
.loading-indicator {
  will-change: contents;
}

.loading-dots {
  will-change: transform;
}

.animate-bounce-dot {
  display: inline-block;
  animation: dot-animation 1.2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

/* Subtle glow effect when heartbeat is active — proves backend is alive */
.heartbeat-active .animate-bounce-dot {
  animation: dot-animation-heartbeat 1.2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

.loading-text {
  opacity: 0;
  animation: fade-in-text 0.4s ease-out 0.2s forwards;
}

@keyframes dot-animation {
  0%, 60%, 100% {
    transform: translateY(0) scale(1);
    opacity: 0.7;
  }
  30% {
    transform: translateY(-3px) scale(1.1);
    opacity: 1;
  }
}

@keyframes dot-animation-heartbeat {
  0%, 60%, 100% {
    transform: translateY(0) scale(1);
    opacity: 0.8;
  }
  30% {
    transform: translateY(-3px) scale(1.15);
    opacity: 1;
  }
}

@keyframes fade-in-text {
  to {
    opacity: 1;
  }
}
</style>
```

**Step 4: Pass `pulse` prop from ChatPage where LoadingIndicator is used**

Find where `LoadingIndicator` is used in ChatPage and pass the `pulse` prop:

```html
<LoadingIndicator :text="loadingText" :pulse="isReceivingHeartbeats" />
```

(Exact location depends on current usage — grep for `<LoadingIndicator` in ChatPage.)

**Step 5: Verify TypeScript compiles**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -10`

**Step 6: Commit**

```bash
git add frontend/src/pages/ChatPage.vue frontend/src/components/ui/LoadingIndicator.vue
git commit -m "feat(chat): integrate heartbeat visual feedback and refine stale detection"
```

---

## Task 6: Add CSS Transitions for Suggestions

**Files:**
- Modify: `frontend/src/components/Suggestions.vue` (add fade-in animation)

**Step 1: Add fade-in transition to Suggestions component**

Add to the `<style scoped>` section at the end of `Suggestions.vue`:

```css
/* Fade-in animation when suggestions appear */
.suggestions-container {
  animation: suggestions-fade-in 0.3s ease-out;
}

@keyframes suggestions-fade-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/Suggestions.vue
git commit -m "feat(suggestions): add fade-in animation on appearance"
```

---

## Task 7: Update Stale Notice Styling

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue:150-171` (stale notice template)

**Step 1: Update the stale notice to be less alarming**

Replace the existing stale notice (lines 150-171):

```html
          <!-- Still working notice - heartbeats arriving but no real events -->
          <div
            v-if="isStale && isLoading"
            class="stale-notice flex items-center gap-3 px-4 py-3 mx-4 mb-2 rounded-xl border border-blue-200 dark:border-blue-800/40 bg-blue-50 dark:bg-blue-950/20 transition-all duration-300"
            role="status"
          >
            <div class="stale-pulse w-2.5 h-2.5 rounded-full bg-blue-400 dark:bg-blue-500 flex-shrink-0 animate-pulse" aria-hidden="true"></div>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-blue-800 dark:text-blue-300">
                {{ isReceivingHeartbeats ? $t('Still working on your request...') : $t('Connection may be unstable...') }}
              </span>
              <span v-if="currentToolInfo" class="text-xs opacity-80 ml-1.5">
                ({{ currentToolInfo.name }})
              </span>
            </div>
            <button
              @click="handleStop"
              class="stale-stop-btn flex-shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
            >
              {{ $t('Stop') }}
            </button>
          </div>
```

**Step 2: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "feat(chat): improve stale notice with heartbeat-aware messaging and calmer styling"
```

---

## Task 8: Fix `restoreSession` and Other Edge Cases

**Files:**
- Modify: `frontend/src/pages/ChatPage.vue` (restoreSession, session loading)

**Step 1: Ensure `restoreSession()` sets proper phase**

In `restoreSession()` (line 2330), when reconnecting to a running session, set the phase:

After the line `realTime.value = true;` (line 2353), update:

```typescript
  if (sessionStatus.value === SessionStatus.INITIALIZING) {
    await waitForSessionIfInitializing();
  }
  if (sessionStatus.value === SessionStatus.RUNNING || sessionStatus.value === SessionStatus.PENDING) {
    transitionTo('connecting') // Will transition to 'streaming' on first event
    receivedDoneEvent.value = false;
```

For completed sessions (when replaying events sets status to COMPLETED via DoneEvent handler), the `transitionTo('completing')` → auto `'settled'` will handle it correctly.

**Step 2: Reset `responsePhase` when starting a brand new session**

In the existing state reset flow (inside `createInitialState`), `responsePhase` defaults to `'idle'` already. Verify that `Object.assign(state, createInitialState())` (if used for full reset) or any new-session path properly resets the phase.

**Step 3: Verify all edge cases compile**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20`

**Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.vue
git commit -m "fix(chat): handle restoreSession and edge cases with responsePhase"
```

---

## Task 9: Lint and Type-Check

**Files:**
- All modified files

**Step 1: Run ESLint**

Run: `cd frontend && bun run lint`

Fix any lint errors that appear.

**Step 2: Run TypeScript check**

Run: `cd frontend && bun run type-check`

Fix any type errors that appear.

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix lint and type-check errors from responsePhase refactor"
```

---

## Task 10: Manual Smoke Test

**No code changes — verification only.**

**Step 1: Start the dev stack**

Run: `./dev.sh up -d`

**Step 2: Test normal completion flow**

1. Open http://localhost:5174
2. Send a simple question like "What is Python?"
3. Verify: Loading indicator shows → response streams → suggestions fade in smoothly after completion
4. Verify: No suggestions appear during streaming

**Step 3: Test greeting fast path**

1. Send "Hello"
2. Verify: Short reply appears with completion footer
3. Verify: NO "Suggested follow-ups" appear for greetings

**Step 4: Test stop behavior**

1. Send a complex query like "Research the latest AI papers"
2. Click "Stop" during execution
3. Verify: Loading stops immediately, NO suggestions appear, input re-enabled

**Step 5: Test timeout behavior (simulate)**

1. Open browser dev tools → Network tab
2. During a running query, throttle network to "Offline"
3. Verify: After timeout, amber "Connection interrupted" banner appears (NOT red error)
4. Verify: NO suggestions appear
5. Verify: "Retry" button is visible

**Step 6: Document results**

Note any issues found for follow-up fixes.

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add `responsePhase` type, ref, computed properties | ChatPage.vue |
| 2 | Replace all direct boolean assignments with `transitionTo()` | ChatPage.vue |
| 3 | Update template: `canShowSuggestions`, timeout banner, retry handler | ChatPage.vue |
| 4 | Skip fallback suggestions for greetings | ChatPage.vue |
| 5 | Heartbeat visual integration + refined stale detection | ChatPage.vue, LoadingIndicator.vue |
| 6 | Suggestions fade-in CSS | Suggestions.vue |
| 7 | Stale notice styling improvements | ChatPage.vue |
| 8 | Fix restoreSession and edge cases | ChatPage.vue |
| 9 | Lint + type-check pass | All files |
| 10 | Manual smoke test | None (verification) |
