import { ref } from 'vue';
import { SessionStatus } from '../types/response';

// Simple event emitter for session status changes
type StatusChangeCallback = (sessionId: string, status: SessionStatus) => void;

const listeners = ref<StatusChangeCallback[]>([]);

/**
 * Composable for managing real-time session status updates across components.
 *
 * This enables immediate UI updates when a session's status changes (e.g., task completes)
 * without waiting for the next SSE poll interval.
 */
export function useSessionStatus() {
  /**
   * Emit a session status change event.
   * Call this when a session's status changes (e.g., task completes, errors, or is stopped).
   */
  const emitStatusChange = (sessionId: string, status: SessionStatus) => {
    listeners.value.forEach(callback => callback(sessionId, status));
  };

  /**
   * Subscribe to session status change events.
   * Returns an unsubscribe function.
   */
  const onStatusChange = (callback: StatusChangeCallback): (() => void) => {
    listeners.value.push(callback);
    return () => {
      const index = listeners.value.indexOf(callback);
      if (index > -1) {
        listeners.value.splice(index, 1);
      }
    };
  };

  return {
    emitStatusChange,
    onStatusChange,
  };
}
