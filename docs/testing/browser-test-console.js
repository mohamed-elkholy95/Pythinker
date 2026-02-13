// Browser Console Test Commands for Auto-Retry and Status Reconciliation
// Copy and paste these into your browser console while testing

// ============================================================================
// INSPECTION COMMANDS - Check Current State
// ============================================================================

// Check all relevant state values
function checkState() {
  console.group('🔍 Current State');
  console.log('responsePhase:', responsePhase?.value);
  console.log('autoRetryCount:', autoRetryCount?.value);
  console.log('autoRetryTimer:', autoRetryTimer?.value ? 'ACTIVE' : 'null');
  console.log('lastError:', lastError?.value);
  console.log('sessionStatus:', sessionStatus?.value);
  console.log('sessionId:', sessionId?.value);
  console.log('receivedDoneEvent:', receivedDoneEvent?.value);
  console.log('lastEventId:', lastEventId?.value);
  console.log('isStale:', isStale?.value);
  console.log('lastHeartbeatAt:', lastHeartbeatAt?.value ? new Date(lastHeartbeatAt.value) : 'never');
  console.groupEnd();
}

// Quick state check (minimal)
function quickState() {
  console.log(`Phase: ${responsePhase?.value} | Retry: ${autoRetryCount?.value}/3 | Status: ${sessionStatus?.value}`);
}

// Monitor state changes in real-time
function watchState() {
  console.log('👀 Watching state changes (check every 2s, Ctrl+C to stop)...');
  const interval = setInterval(() => {
    quickState();
  }, 2000);

  // Store interval for cleanup
  window._stateWatchInterval = interval;
  console.log('To stop: clearInterval(window._stateWatchInterval)');
}

// ============================================================================
// TEST TRIGGER COMMANDS - Simulate Scenarios
// ============================================================================

// Simulate timeout (DEV ONLY - for testing state machine)
function simulateTimeout() {
  console.warn('⚠️ Simulating timeout state...');
  transitionTo('timed_out');
  console.log('✓ Transitioned to timed_out - auto-retry should trigger');
}

// Simulate error (DEV ONLY)
function simulateError(message = 'Test error', type = 'test', recoverable = true) {
  console.warn('⚠️ Simulating error state...');
  lastError.value = {
    message,
    type,
    recoverable,
    hint: 'This is a test error'
  };
  transitionTo('error');
  console.log('✓ Transitioned to error state');
}

// Cancel current auto-retry timer
function cancelAutoRetry() {
  if (autoRetryTimer?.value) {
    clearTimeout(autoRetryTimer.value);
    autoRetryTimer.value = null;
    console.log('✓ Auto-retry timer cancelled');
  } else {
    console.log('ℹ️ No active auto-retry timer');
  }
}

// Reset auto-retry count
function resetRetryCount() {
  autoRetryCount.value = 0;
  console.log('✓ Auto-retry count reset to 0');
}

// ============================================================================
// VALIDATION COMMANDS - Check Implementation
// ============================================================================

// Check if state machine guards are working
function testStateTransitions() {
  console.group('🧪 Testing State Machine Transitions');

  const currentPhase = responsePhase?.value;
  console.log('Current phase:', currentPhase);

  // Try invalid transition
  console.log('\n Testing invalid transition: settled → timed_out');
  if (currentPhase === 'settled') {
    transitionTo('timed_out');
    console.log('Result:', responsePhase?.value === 'timed_out' ? '❌ BLOCKED failed!' : '✅ Correctly blocked');
  } else {
    console.log('⏭️ Skipped (not in settled state)');
  }

  console.groupEnd();
}

// Check if cleanup helper exists
function checkCleanupHelper() {
  console.group('🧪 Checking Implementation');
  console.log('cleanupStreamingState:', typeof cleanupStreamingState === 'function' ? '✅ Implemented' : '❌ Missing');
  console.log('setLastErrorFromTransportError:', typeof setLastErrorFromTransportError === 'function' ? '✅ Implemented' : '❌ Missing');
  console.log('VALID_TRANSITIONS:', typeof VALID_TRANSITIONS !== 'undefined' ? '✅ Implemented' : '❌ Missing');
  console.groupEnd();
}

// Check auto-retry configuration
function checkAutoRetryConfig() {
  console.group('⚙️ Auto-Retry Configuration');
  console.log('AUTO_RETRY_DELAYS_MS:', AUTO_RETRY_DELAYS_MS || 'Not accessible in scope');
  console.log('Max retries: 3 (hardcoded)');
  console.log('Delays: [5000, 15000, 45000] ms');
  console.groupEnd();
}

// ============================================================================
// MONITORING COMMANDS - Track Behavior
// ============================================================================

// Log all state transitions
function logTransitions() {
  console.log('📊 Logging all state transitions...');

  const originalTransitionTo = transitionTo;
  window._originalTransitionTo = originalTransitionTo;

  transitionTo = function(phase) {
    console.log(`[TRANSITION] ${responsePhase?.value} → ${phase}`);
    return originalTransitionTo(phase);
  };

  console.log('✓ Transition logging enabled');
  console.log('To restore: transitionTo = window._originalTransitionTo');
}

// Track error events
function trackErrors() {
  console.log('🔴 Tracking error events...');

  window.addEventListener('error', (e) => {
    console.error('[JS ERROR]', e.message, e.filename, e.lineno);
  });

  window.addEventListener('unhandledrejection', (e) => {
    console.error('[UNHANDLED PROMISE]', e.reason);
  });

  console.log('✓ Error tracking enabled');
}

// ============================================================================
// HELPER UTILITIES
// ============================================================================

// Get current session info
function getSessionInfo() {
  return {
    sessionId: sessionId?.value,
    status: sessionStatus?.value,
    phase: responsePhase?.value,
    lastEventId: lastEventId?.value,
  };
}

// Get session from sessionStorage
function getStoredSession() {
  const id = sessionId?.value;
  if (!id) return null;

  return {
    lastEventId: sessionStorage.getItem(`pythinker-last-event-${id}`),
    stoppedFlag: sessionStorage.getItem(`pythinker-stopped-${id}`),
  };
}

// Clear session storage for current session
function clearSessionStorage() {
  const id = sessionId?.value;
  if (!id) {
    console.log('No active session');
    return;
  }

  sessionStorage.removeItem(`pythinker-last-event-${id}`);
  sessionStorage.removeItem(`pythinker-stopped-${id}`);
  console.log(`✓ Cleared session storage for ${id}`);
}

// ============================================================================
// QUICK START GUIDE
// ============================================================================

console.log(`
╔════════════════════════════════════════════════════════════╗
║  Pythinker Auto-Retry Test Console                        ║
╚════════════════════════════════════════════════════════════╝

📋 QUICK COMMANDS:

State Inspection:
  checkState()           - Show all state values
  quickState()           - Quick one-line state check
  watchState()           - Monitor state changes (every 2s)

Testing:
  simulateTimeout()      - Trigger timeout state
  simulateError()        - Trigger error state
  cancelAutoRetry()      - Cancel pending auto-retry
  resetRetryCount()      - Reset retry counter

Validation:
  testStateTransitions() - Test state machine guards
  checkCleanupHelper()   - Verify implementation
  checkAutoRetryConfig() - Show auto-retry settings

Monitoring:
  logTransitions()       - Log all state transitions
  trackErrors()          - Track JavaScript errors

Utilities:
  getSessionInfo()       - Get current session data
  getStoredSession()     - Get sessionStorage data
  clearSessionStorage()  - Clear session data

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 QUICK START:
  1. Run: checkState()
  2. Start a task in the UI
  3. Run: watchState()
  4. Go offline in Network tab
  5. Watch auto-retry in console

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`);

// Auto-run on load
if (typeof responsePhase !== 'undefined') {
  console.log('✅ Connected to ChatPage component');
  quickState();
} else {
  console.warn('⚠️ ChatPage component not found - navigate to /chat page');
}
