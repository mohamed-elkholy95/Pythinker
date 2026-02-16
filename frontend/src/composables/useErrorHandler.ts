import { ref, computed, Ref } from 'vue';
import type { ToolContent } from '../types/message';

/**
 * Error state interface
 */
export interface ErrorState {
  hasError: boolean;
  errorMessage: string | null;
  retryable: boolean;
  errorTimestamp: number | null;
}

/**
 * Composable for handling errors in tool views
 *
 * @param toolContent - Optional reactive reference to current tool content
 * @returns Error state management utilities
 *
 * @example
 * ```ts
 * const { errorState, setError, clearError, retry } = useErrorHandler(toolContent);
 *
 * // Set error
 * setError('Failed to fetch data', { retryable: true });
 *
 * // Clear error
 * clearError();
 *
 * // Retry with callback
 * retry(() => fetchData());
 * ```
 */
export function useErrorHandler(toolContent?: Ref<ToolContent | undefined>) {
  const errorMessage = ref<string | null>(null);
  const retryable = ref(false);
  const errorTimestamp = ref<number | null>(null);
  const retryCallback = ref<(() => void | Promise<void>) | null>(null);
  const retryCount = ref(0);

  const hasError = computed(() => errorMessage.value !== null);

  /**
   * Combined error state object
   */
  const errorState = computed<ErrorState>(() => ({
    hasError: hasError.value,
    errorMessage: errorMessage.value,
    retryable: retryable.value,
    errorTimestamp: errorTimestamp.value,
  }));

  /**
   * Detect error from tool content
   * Note: ToolContent status is only "calling" | "called", errors are in content
   */
  const toolHasError = computed(() => {
    if (!toolContent?.value) return false;
    const content = toolContent.value.content;
    if (content && typeof content === 'object' && 'error' in content) {
      return true;
    }
    return false;
  });

  /**
   * Extract error message from tool content
   */
  const toolErrorMessage = computed(() => {
    if (!toolContent?.value) return null;
    const content = toolContent.value.content;
    if (typeof content === 'string') return content;
    if (content && typeof content === 'object' && 'error' in content) {
      return String(content.error);
    }
    return null;
  });

  /**
   * Set error state
   */
  function setError(
    message: string,
    options?: {
      retryable?: boolean;
      onRetry?: () => void | Promise<void>;
    }
  ) {
    errorMessage.value = message;
    retryable.value = options?.retryable || false;
    errorTimestamp.value = Date.now();
    if (options?.onRetry) {
      retryCallback.value = options.onRetry;
    }
  }

  /**
   * Clear error state
   */
  function clearError() {
    errorMessage.value = null;
    retryable.value = false;
    errorTimestamp.value = null;
    retryCallback.value = null;
    retryCount.value = 0;
  }

  /**
   * Retry the failed operation
   */
  async function retry() {
    if (retryCallback.value) {
      // Save callback and count before clearing
      const callback = retryCallback.value;
      const currentCount = retryCount.value;

      // Clear error state but preserve callback for retry
      errorMessage.value = null;
      retryable.value = false;
      errorTimestamp.value = null;
      // Don't clear retryCallback or retryCount during retry

      retryCount.value = currentCount + 1;

      try {
        await callback();
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message, { retryable: true, onRetry: callback });
      }
    }
  }

  /**
   * Check if error is recent (within last 5 seconds)
   */
  const isRecentError = computed(() => {
    if (!errorTimestamp.value) return false;
    return Date.now() - errorTimestamp.value < 5000;
  });

  /**
   * Categorize error type based on message
   */
  const errorCategory = computed<'network' | 'timeout' | 'validation' | 'server' | 'unknown'>(() => {
    if (!errorMessage.value) return 'unknown';
    const msg = errorMessage.value.toLowerCase();

    if (msg.includes('network') || msg.includes('connection') || msg.includes('fetch')) {
      return 'network';
    }
    if (msg.includes('timeout') || msg.includes('timed out')) {
      return 'timeout';
    }
    if (msg.includes('validation') || msg.includes('invalid')) {
      return 'validation';
    }
    if (msg.includes('500') || msg.includes('server') || msg.includes('internal error')) {
      return 'server';
    }

    return 'unknown';
  });

  return {
    // State
    errorState,
    hasError,
    errorMessage,
    retryable,
    errorTimestamp,
    retryCount,
    isRecentError,
    errorCategory,

    // Tool-derived state
    toolHasError,
    toolErrorMessage,

    // Methods
    setError,
    clearError,
    retry,
  };
}
