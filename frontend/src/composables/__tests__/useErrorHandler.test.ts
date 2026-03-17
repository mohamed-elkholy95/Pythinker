import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ref, nextTick } from 'vue';
import { useErrorHandler } from '../useErrorHandler';
import type { ToolContent } from '@/types/message';

describe('useErrorHandler', () => {
  let toolContent: ReturnType<typeof ref<ToolContent | undefined>>;

  beforeEach(() => {
    toolContent = ref<ToolContent | undefined>();
    vi.clearAllMocks();
  });

  describe('initialization', () => {
    it('should initialize with no error', () => {
      const { errorState, hasError } = useErrorHandler();

      expect(hasError.value).toBe(false);
      expect(errorState.value.hasError).toBe(false);
      expect(errorState.value.errorMessage).toBeNull();
      expect(errorState.value.retryable).toBe(false);
      expect(errorState.value.errorTimestamp).toBeNull();
    });

    it('should not detect error when tool content is undefined', () => {
      const { toolHasError } = useErrorHandler(toolContent);

      expect(toolHasError.value).toBe(false);
    });
  });

  describe('setError', () => {
    it('should set error state with message only', () => {
      const { setError, errorState } = useErrorHandler();

      setError('Something went wrong');

      expect(errorState.value.hasError).toBe(true);
      expect(errorState.value.errorMessage).toBe('Something went wrong');
      expect(errorState.value.retryable).toBe(false);
      expect(errorState.value.errorTimestamp).toBeGreaterThan(0);
    });

    it('should set error state with retryable option', () => {
      const { setError, errorState, retryable } = useErrorHandler();

      setError('Network error', { retryable: true });

      expect(errorState.value.retryable).toBe(true);
      expect(retryable.value).toBe(true);
    });

    it('should set error state with retry callback', () => {
      const { setError, errorState } = useErrorHandler();
      const onRetry = vi.fn();

      setError('Failed', { retryable: true, onRetry });

      expect(errorState.value.hasError).toBe(true);
      expect(errorState.value.retryable).toBe(true);
    });
  });

  describe('clearError', () => {
    it('should clear error state', () => {
      const { setError, clearError, errorState, retryCount } = useErrorHandler();

      setError('Error', { retryable: true });
      expect(errorState.value.hasError).toBe(true);

      clearError();

      expect(errorState.value.hasError).toBe(false);
      expect(errorState.value.errorMessage).toBeNull();
      expect(errorState.value.retryable).toBe(false);
      expect(errorState.value.errorTimestamp).toBeNull();
      expect(retryCount.value).toBe(0);
    });
  });

  describe('retry', () => {
    it('should call retry callback and increment count', async () => {
      const { setError, retry, retryCount } = useErrorHandler();
      const onRetry = vi.fn().mockResolvedValue(undefined);

      setError('Failed', { retryable: true, onRetry });

      await retry();

      expect(onRetry).toHaveBeenCalledTimes(1);
      expect(retryCount.value).toBe(1);
    });

    it('should clear error before retrying', async () => {
      const { setError, retry, hasError } = useErrorHandler();
      const onRetry = vi.fn().mockResolvedValue(undefined);

      setError('Failed', { retryable: true, onRetry });
      expect(hasError.value).toBe(true);

      await retry();

      expect(hasError.value).toBe(false);
    });

    it('should handle retry failure and set error again', async () => {
      const { setError, retry, hasError, errorMessage } = useErrorHandler();
      const onRetry = vi.fn().mockRejectedValue(new Error('Retry failed'));

      setError('Initial error', { retryable: true, onRetry });

      await retry();

      expect(hasError.value).toBe(true);
      expect(errorMessage.value).toBe('Retry failed');
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it('should do nothing if no retry callback is set', async () => {
      const { setError, retry, retryCount } = useErrorHandler();

      setError('Failed', { retryable: false });

      await retry();

      expect(retryCount.value).toBe(0);
    });

    it('should preserve retry callback after retry', async () => {
      const { setError, retry } = useErrorHandler();
      const onRetry = vi.fn().mockResolvedValue(undefined);

      setError('Failed', { retryable: true, onRetry });

      await retry();
      expect(onRetry).toHaveBeenCalledTimes(1);

      await retry();
      expect(onRetry).toHaveBeenCalledTimes(2);
    });
  });

  describe('isRecentError', () => {
    it('should be true for errors within 5 seconds', () => {
      const { setError, isRecentError } = useErrorHandler();

      setError('Recent error');

      expect(isRecentError.value).toBe(true);
    });

    it('should be false when no error exists', () => {
      const { isRecentError } = useErrorHandler();

      expect(isRecentError.value).toBe(false);
    });

    it('should be false for old errors', () => {
      const { setError, isRecentError, errorTimestamp } = useErrorHandler();

      setError('Old error');

      // Manually set timestamp to 10 seconds ago
      errorTimestamp.value = Date.now() - 10000;

      expect(isRecentError.value).toBe(false);
    });
  });

  describe('errorCategory', () => {
    it('should categorize network errors', () => {
      const { setError, errorCategory } = useErrorHandler();

      setError('Network connection failed');
      expect(errorCategory.value).toBe('network');

      setError('Fetch request failed');
      expect(errorCategory.value).toBe('network');
    });

    it('should categorize timeout errors', () => {
      const { setError, errorCategory } = useErrorHandler();

      setError('Request timed out');
      expect(errorCategory.value).toBe('timeout');

      setError('Operation timeout exceeded');
      expect(errorCategory.value).toBe('timeout');
    });

    it('should categorize validation errors', () => {
      const { setError, errorCategory } = useErrorHandler();

      setError('Validation failed');
      expect(errorCategory.value).toBe('validation');

      setError('Invalid input provided');
      expect(errorCategory.value).toBe('validation');
    });

    it('should categorize server errors', () => {
      const { setError, errorCategory } = useErrorHandler();

      setError('Internal server error 500');
      expect(errorCategory.value).toBe('server');

      setError('Server unavailable');
      expect(errorCategory.value).toBe('server');
    });

    it('should categorize unknown errors', () => {
      const { setError, errorCategory } = useErrorHandler();

      setError('Something unexpected happened');
      expect(errorCategory.value).toBe('unknown');
    });
  });

  describe('tool content integration', () => {
    it('should detect error in tool content', async () => {
      const { toolHasError, toolErrorMessage } = useErrorHandler(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        content: { error: 'Navigation failed' },
        timestamp: Date.now(),
      };

      await nextTick();

      expect(toolHasError.value).toBe(true);
      expect(toolErrorMessage.value).toBe('Navigation failed');
    });

    it('should handle string content as error message', async () => {
      const { toolErrorMessage } = useErrorHandler(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        content: 'Error message string' as any,
        timestamp: Date.now(),
      };

      await nextTick();

      expect(toolErrorMessage.value).toBe('Error message string');
    });

    it('should return null when no error in content', async () => {
      const { toolHasError, toolErrorMessage } = useErrorHandler(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        content: { result: 'success' },
        timestamp: Date.now(),
      };

      await nextTick();

      expect(toolHasError.value).toBe(false);
      expect(toolErrorMessage.value).toBeNull();
    });
  });

  describe('error state object', () => {
    it('should provide combined error state', () => {
      const { setError, errorState } = useErrorHandler();
      const timestamp = Date.now();

      setError('Test error', { retryable: true });

      expect(errorState.value).toMatchObject({
        hasError: true,
        errorMessage: 'Test error',
        retryable: true,
      });
      expect(errorState.value.errorTimestamp).toBeGreaterThanOrEqual(timestamp);
    });
  });
});
