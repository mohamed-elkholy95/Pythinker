import { describe, it, expect, beforeEach } from 'vitest';
import { ref } from 'vue';
import { useLoadingState } from '../useLoadingState';
import type { ToolContent } from '@/types/message';

describe('useLoadingState', () => {
  let toolContent: ReturnType<typeof ref<ToolContent | undefined>>;

  beforeEach(() => {
    toolContent = ref<ToolContent | undefined>();
  });

  describe('initialization', () => {
    it('should initialize with default loading state', () => {
      const { loadingState, isLoading } = useLoadingState();

      expect(isLoading.value).toBe(false);
      expect(loadingState.value.label).toBe('Loading');
      expect(loadingState.value.animation).toBe('spinner');
      expect(loadingState.value.isActive).toBe(true);
      expect(loadingState.value.detail).toBeUndefined();
    });

    it('should detect tool execution when status is calling', () => {
      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      const { isToolExecuting } = useLoadingState(toolContent);

      expect(isToolExecuting.value).toBe(true);
    });

    it('should not detect execution when status is called', () => {
      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        timestamp: Date.now(),
      };

      const { isToolExecuting } = useLoadingState(toolContent);

      expect(isToolExecuting.value).toBe(false);
    });
  });

  describe('setLoading', () => {
    it('should set loading state with label only', () => {
      const { setLoading, loadingState, isLoading } = useLoadingState();

      setLoading('Fetching data');

      expect(isLoading.value).toBe(true);
      expect(loadingState.value.label).toBe('Fetching data');
      expect(loadingState.value.animation).toBe('spinner');
      expect(loadingState.value.isActive).toBe(true);
    });

    it('should set loading state with all options', () => {
      const { setLoading, loadingState } = useLoadingState();

      setLoading('Searching', {
        detail: 'example query',
        animation: 'search',
        isActive: true,
      });

      expect(loadingState.value.label).toBe('Searching');
      expect(loadingState.value.detail).toBe('example query');
      expect(loadingState.value.animation).toBe('search');
      expect(loadingState.value.isActive).toBe(true);
    });

    it('should handle all animation types', () => {
      const { setLoading, loadingState } = useLoadingState();

      const animations = ['globe', 'search', 'file', 'terminal', 'code', 'spinner', 'check'] as const;

      animations.forEach((anim) => {
        setLoading('Loading', { animation: anim });
        expect(loadingState.value.animation).toBe(anim);
      });
    });
  });

  describe('clearLoading', () => {
    it('should clear loading state', () => {
      const { setLoading, clearLoading, isLoading, detail } = useLoadingState();

      setLoading('Loading', { detail: 'test detail' });
      expect(isLoading.value).toBe(true);
      expect(detail.value).toBe('test detail');

      clearLoading();

      expect(isLoading.value).toBe(false);
      expect(detail.value).toBeUndefined();
    });
  });

  describe('updateDetail', () => {
    it('should update only the detail', () => {
      const { setLoading, updateDetail, loadingState } = useLoadingState();

      setLoading('Loading', { detail: 'initial' });
      expect(loadingState.value.detail).toBe('initial');

      updateDetail('updated');
      expect(loadingState.value.detail).toBe('updated');
      expect(loadingState.value.label).toBe('Loading');
    });

    it('should clear detail when undefined', () => {
      const { setLoading, updateDetail, detail } = useLoadingState();

      setLoading('Loading', { detail: 'initial' });
      expect(detail.value).toBe('initial');

      updateDetail(undefined);
      expect(detail.value).toBeUndefined();
    });
  });

  describe('updateAnimation', () => {
    it('should update only the animation type', () => {
      const { setLoading, updateAnimation, loadingState } = useLoadingState();

      setLoading('Loading', { animation: 'spinner' });
      expect(loadingState.value.animation).toBe('spinner');

      updateAnimation('globe');
      expect(loadingState.value.animation).toBe('globe');
      expect(loadingState.value.label).toBe('Loading');
    });
  });

  describe('reactive updates', () => {
    it('should react to tool content changes', () => {
      const { isToolExecuting } = useLoadingState(toolContent);

      expect(isToolExecuting.value).toBe(false);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      expect(isToolExecuting.value).toBe(true);

      toolContent.value.status = 'called';

      expect(isToolExecuting.value).toBe(false);
    });
  });

  describe('individual property access', () => {
    it('should provide direct access to label', () => {
      const { setLoading, label } = useLoadingState();

      setLoading('Test Label');

      expect(label.value).toBe('Test Label');
    });

    it('should provide direct access to animation', () => {
      const { setLoading, animation } = useLoadingState();

      setLoading('Loading', { animation: 'file' });

      expect(animation.value).toBe('file');
    });

    it('should provide direct access to isActive', () => {
      const { setLoading, isActive } = useLoadingState();

      setLoading('Loading', { isActive: false });

      expect(isActive.value).toBe(false);
    });
  });
});
