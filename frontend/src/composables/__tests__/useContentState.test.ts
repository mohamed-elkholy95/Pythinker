import { describe, it, expect, beforeEach } from 'vitest';
import { ref, nextTick } from 'vue';
import { useContentState } from '../useContentState';
import type { ToolContent } from '@/types/message';

describe('useContentState', () => {
  let toolContent: ReturnType<typeof ref<ToolContent | undefined>>;

  beforeEach(() => {
    toolContent = ref<ToolContent | undefined>();
  });

  describe('initialization', () => {
    it('should initialize with loading state when no tool content', () => {
      const { contentState } = useContentState();

      expect(contentState.value.type).toBe('loading');
      expect(contentState.value.isLoading).toBe(true);
      expect(contentState.value.hasError).toBe(false);
      expect(contentState.value.isEmpty).toBe(false);
      expect(contentState.value.isReady).toBe(false);
    });

    it('should initialize with empty state when tool content is provided but undefined', async () => {
      const { contentState } = useContentState(toolContent);

      await nextTick();

      expect(contentState.value.type).toBe('empty');
      expect(contentState.value.isEmpty).toBe(true);
    });
  });

  describe('state transitions', () => {
    it('should transition to loading state', () => {
      const { setLoading, contentState } = useContentState();

      setLoading();

      expect(contentState.value.type).toBe('loading');
      expect(contentState.value.isLoading).toBe(true);
      expect(contentState.value.content).toBeNull();
    });

    it('should transition to error state', () => {
      const { setError, contentState } = useContentState();

      setError('Something failed');

      expect(contentState.value.type).toBe('error');
      expect(contentState.value.hasError).toBe(true);
      expect(contentState.value.content).toBe('Something failed');
    });

    it('should transition to empty state', () => {
      const { setEmpty, contentState } = useContentState();

      setEmpty();

      expect(contentState.value.type).toBe('empty');
      expect(contentState.value.isEmpty).toBe(true);
      expect(contentState.value.content).toBeNull();
    });

    it('should transition to ready state with content', () => {
      const { setReady, contentState } = useContentState();
      const data = { result: 'success', value: 42 };

      setReady(data);

      expect(contentState.value.type).toBe('ready');
      expect(contentState.value.isReady).toBe(true);
      expect(contentState.value.content).toEqual(data);
    });
  });

  describe('reset', () => {
    it('should reset to loading state', () => {
      const { setReady, reset, contentState } = useContentState();

      setReady({ data: 'test' });
      expect(contentState.value.type).toBe('ready');

      reset();

      expect(contentState.value.type).toBe('loading');
      expect(contentState.value.isLoading).toBe(true);
    });
  });

  describe('boolean flags', () => {
    it('should have correct flags for loading state', () => {
      const { setLoading, isLoading, hasError, isEmpty, isReady } = useContentState();

      setLoading();

      expect(isLoading.value).toBe(true);
      expect(hasError.value).toBe(false);
      expect(isEmpty.value).toBe(false);
      expect(isReady.value).toBe(false);
    });

    it('should have correct flags for error state', () => {
      const { setError, isLoading, hasError, isEmpty, isReady } = useContentState();

      setError('Error');

      expect(isLoading.value).toBe(false);
      expect(hasError.value).toBe(true);
      expect(isEmpty.value).toBe(false);
      expect(isReady.value).toBe(false);
    });

    it('should have correct flags for empty state', () => {
      const { setEmpty, isLoading, hasError, isEmpty, isReady } = useContentState();

      setEmpty();

      expect(isLoading.value).toBe(false);
      expect(hasError.value).toBe(false);
      expect(isEmpty.value).toBe(true);
      expect(isReady.value).toBe(false);
    });

    it('should have correct flags for ready state', () => {
      const { setReady, isLoading, hasError, isEmpty, isReady } = useContentState();

      setReady({ data: 'test' });

      expect(isLoading.value).toBe(false);
      expect(hasError.value).toBe(false);
      expect(isEmpty.value).toBe(false);
      expect(isReady.value).toBe(true);
    });
  });

  describe('tool content auto-updates', () => {
    it('should auto-update to loading when tool status is calling', async () => {
      const { contentState } = useContentState(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(contentState.value.type).toBe('loading');
      expect(contentState.value.isLoading).toBe(true);
    });

    it('should auto-update to ready when tool completes with content', async () => {
      const { contentState } = useContentState(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        content: { result: 'Navigation successful' },
        timestamp: Date.now(),
      };

      await nextTick();

      expect(contentState.value.type).toBe('ready');
      expect(contentState.value.isReady).toBe(true);
    });

    it('should auto-update to empty when tool completes without content', async () => {
      const { contentState } = useContentState(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(contentState.value.type).toBe('empty');
      expect(contentState.value.isEmpty).toBe(true);
    });

    it('should auto-update to error when tool content has error', async () => {
      const { contentState } = useContentState(toolContent);

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

      expect(contentState.value.type).toBe('error');
      expect(contentState.value.hasError).toBe(true);
    });

    it('should auto-update to empty when tool content is undefined', async () => {
      const { contentState } = useContentState(toolContent);

      toolContent.value = undefined;

      await nextTick();

      expect(contentState.value.type).toBe('empty');
    });
  });

  describe('hasToolContent computed', () => {
    it('should detect object content', async () => {
      const { hasToolContent } = useContentState(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        content: { result: 'data' },
        timestamp: Date.now(),
      };

      await nextTick();

      expect(hasToolContent.value).toBe(true);
    });

    it('should detect empty object', async () => {
      const { hasToolContent } = useContentState(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        content: {},
        timestamp: Date.now(),
      };

      await nextTick();

      expect(hasToolContent.value).toBe(false);
    });

    it('should return false for null content', async () => {
      const { hasToolContent } = useContentState(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        content: null as any,
        timestamp: Date.now(),
      };

      await nextTick();

      expect(hasToolContent.value).toBe(false);
    });

    it('should return false when no tool content', async () => {
      const { hasToolContent } = useContentState(toolContent);

      await nextTick();

      expect(hasToolContent.value).toBe(false);
    });
  });

  describe('toolStatus computed', () => {
    it('should extract tool status', async () => {
      const { toolStatus } = useContentState(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(toolStatus.value).toBe('calling');
    });

    it('should return null when no tool content', () => {
      const { toolStatus } = useContentState(toolContent);

      expect(toolStatus.value).toBeNull();
    });
  });

  describe('state persistence', () => {
    it('should maintain state across multiple transitions', () => {
      const { setLoading, setReady, setError, contentState } = useContentState();

      setLoading();
      expect(contentState.value.type).toBe('loading');

      setReady({ data: 'test' });
      expect(contentState.value.type).toBe('ready');
      expect(contentState.value.content).toEqual({ data: 'test' });

      setError('Failed');
      expect(contentState.value.type).toBe('error');
      expect(contentState.value.content).toBe('Failed');

      setLoading();
      expect(contentState.value.type).toBe('loading');
      expect(contentState.value.content).toBeNull();
    });
  });

  describe('complex scenarios', () => {
    it('should handle rapid status changes', async () => {
      const { contentState } = useContentState(toolContent);

      // Start calling
      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();
      expect(contentState.value.type).toBe('loading');

      // Complete successfully
      toolContent.value.status = 'called';
      toolContent.value.content = { result: 'success' };

      await nextTick();
      expect(contentState.value.type).toBe('ready');
    });

    it('should handle tool content replacement', async () => {
      const { contentState } = useContentState(toolContent);

      // First tool call
      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        content: { result: 'first' },
        timestamp: Date.now(),
      };

      await nextTick();
      expect(contentState.value.content).toEqual({ result: 'first' });

      // Second tool call
      toolContent.value = {
        tool_call_id: 'test-2',
        name: 'search',
        function: 'search',
        args: {},
        status: 'called',
        content: { result: 'second' },
        timestamp: Date.now(),
      };

      await nextTick();
      expect(contentState.value.content).toEqual({ result: 'second' });
    });
  });
});
