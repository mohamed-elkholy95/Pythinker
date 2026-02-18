import { ref, onUnmounted } from 'vue';
import { formatRelativeTime, formatCustomTime } from '../utils/time';
import { useI18n } from 'vue-i18n';

/**
 * Module-level shared clock — one interval for the entire app.
 * All components that call useRelativeTime() share this single reactive ref.
 * Updating every 30 seconds keeps relative labels fresh without per-component timers.
 */
const _sharedClock = ref(Date.now());
let _clockTimer: ReturnType<typeof setInterval> | null = null;
let _clockSubscribers = 0;

function _startClock() {
  _clockSubscribers++;
  if (_clockTimer !== null) return;
  _clockTimer = setInterval(() => {
    _sharedClock.value = Date.now();
  }, 30_000);
}

function _stopClock() {
  _clockSubscribers = Math.max(0, _clockSubscribers - 1);
  if (_clockSubscribers === 0 && _clockTimer !== null) {
    clearInterval(_clockTimer);
    _clockTimer = null;
  }
}

/**
 * Returns a `relativeTime(timestamp)` function that reactively updates every 30 s.
 * `timestamp` must be a Unix timestamp in **seconds**.
 *
 * Usage in template: {{ relativeTime(message.content.timestamp) }}
 */
export function useRelativeTime() {
  _startClock();
  onUnmounted(_stopClock);

  /**
   * Plain function — Vue tracks `_sharedClock.value` as a reactive dependency
   * during template rendering, so the component re-renders automatically every 30 s.
   */
  const relativeTime = (timestamp: number | string): string => {
    void _sharedClock.value; // reactive read — establishes render-effect dependency
    return formatRelativeTime(timestamp);
  };

  return { relativeTime };
}

/**
 * Returns a `customTime(timestamp)` function for sidebar/header timestamps.
 * Shows HH:MM for today, day-of-week for this week, MM/DD for this year, etc.
 * `timestamp` must be a Unix timestamp in **seconds**.
 */
export function useCustomTime() {
  const { t, locale } = useI18n();

  _startClock();
  onUnmounted(_stopClock);

  const customTime = (timestamp: number | string): string => {
    void _sharedClock.value; // reactive read
    return formatCustomTime(timestamp, t, locale.value);
  };

  return { customTime };
}
