import { describe, it, expect, beforeEach } from 'vitest';
import { ref, nextTick } from 'vue';
import { useAnimation } from '../useAnimation';
import type { ToolContent } from '@/types/message';
import type { AnimationType } from '../useLoadingState';

describe('useAnimation', () => {
  let toolContent: ReturnType<typeof ref<ToolContent | undefined>>;

  beforeEach(() => {
    toolContent = ref<ToolContent | undefined>();
  });

  describe('getAnimationForTool', () => {
    it('should return correct animation for browser tools', () => {
      const { getAnimationForTool } = useAnimation();

      expect(getAnimationForTool('browser')).toBe('globe');
      expect(getAnimationForTool('browser_agent')).toBe('globe');
    });

    it('should return correct animation for search tools', () => {
      const { getAnimationForTool } = useAnimation();

      expect(getAnimationForTool('search')).toBe('search');
    });

    it('should return correct animation for file tools', () => {
      const { getAnimationForTool } = useAnimation();

      expect(getAnimationForTool('file')).toBe('file');
      expect(getAnimationForTool('file_read')).toBe('file');
      expect(getAnimationForTool('file_write')).toBe('file');
    });

    it('should return correct animation for shell tools', () => {
      const { getAnimationForTool } = useAnimation();

      expect(getAnimationForTool('shell')).toBe('terminal');
    });

    it('should return correct animation for code tools', () => {
      const { getAnimationForTool } = useAnimation();

      expect(getAnimationForTool('code_executor')).toBe('code');
    });

    it('should return spinner as default fallback', () => {
      const { getAnimationForTool } = useAnimation();

      expect(getAnimationForTool('unknown_tool')).toBe('spinner');
      expect(getAnimationForTool()).toBe('spinner');
    });

    it('should prioritize function-specific overrides', () => {
      const { getAnimationForTool } = useAnimation();

      // Function override should take precedence over tool name
      expect(getAnimationForTool('file', 'search_web')).toBe('search');
      expect(getAnimationForTool('unknown', 'browser_navigate')).toBe('globe');
    });
  });

  describe('recommendedAnimation', () => {
    it('should recommend spinner when no tool content', () => {
      const { recommendedAnimation } = useAnimation(toolContent);

      expect(recommendedAnimation.value).toBe('spinner');
    });

    it('should recommend animation based on tool name', async () => {
      const { recommendedAnimation } = useAnimation(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(recommendedAnimation.value).toBe('globe');
    });

    it('should recommend animation based on function override', async () => {
      const { recommendedAnimation } = useAnimation(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'search_web',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(recommendedAnimation.value).toBe('search');
    });

    it('should update when tool content changes', async () => {
      const { recommendedAnimation } = useAnimation(toolContent);

      // Start with browser
      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();
      expect(recommendedAnimation.value).toBe('globe');

      // Change to file
      toolContent.value.name = 'file';
      toolContent.value.function = 'file_read';

      await nextTick();
      expect(recommendedAnimation.value).toBe('file');
    });
  });

  describe('isAnimationActive', () => {
    it('should be false when no tool content', () => {
      const { isAnimationActive } = useAnimation(toolContent);

      expect(isAnimationActive.value).toBe(false);
    });

    it('should be true when status is calling', async () => {
      const { isAnimationActive } = useAnimation(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(isAnimationActive.value).toBe(true);
    });

    it('should be false when status is called', async () => {
      const { isAnimationActive } = useAnimation(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'called',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(isAnimationActive.value).toBe(false);
    });

    it('should update when status changes', async () => {
      const { isAnimationActive } = useAnimation(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();
      expect(isAnimationActive.value).toBe(true);

      toolContent.value.status = 'called';

      await nextTick();
      expect(isAnimationActive.value).toBe(false);
    });
  });

  describe('getSuccessAnimation', () => {
    it('should return check animation for success', () => {
      const { getSuccessAnimation } = useAnimation();

      expect(getSuccessAnimation()).toBe('check');
    });
  });

  describe('isTextOnlyOperation', () => {
    it('should detect text-only browser operations', async () => {
      const { isTextOnlyOperation } = useAnimation(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'browser_get_content',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(isTextOnlyOperation.value).toBe(true);
    });

    it('should detect text-only search operations', async () => {
      const { isTextOnlyOperation } = useAnimation(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'search',
        function: 'search_web',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(isTextOnlyOperation.value).toBe(true);
    });

    it('should not detect visual operations as text-only', async () => {
      const { isTextOnlyOperation } = useAnimation(toolContent);

      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'browser_navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(isTextOnlyOperation.value).toBe(false);
    });

    it('should be false when no tool content', () => {
      const { isTextOnlyOperation } = useAnimation(toolContent);

      expect(isTextOnlyOperation.value).toBe(false);
    });
  });

  describe('getAnimationByType', () => {
    it('should map operation types to animations', () => {
      const { getAnimationByType } = useAnimation();

      expect(getAnimationByType('network')).toBe('globe');
      expect(getAnimationByType('search')).toBe('search');
      expect(getAnimationByType('file')).toBe('file');
      expect(getAnimationByType('shell')).toBe('terminal');
      expect(getAnimationByType('code')).toBe('code');
      expect(getAnimationByType('generic')).toBe('spinner');
    });
  });

  describe('availableAnimations', () => {
    it('should provide list of all animation types', () => {
      const { availableAnimations } = useAnimation();

      const expected: AnimationType[] = [
        'globe',
        'search',
        'file',
        'terminal',
        'code',
        'spinner',
        'check',
      ];

      expect(availableAnimations).toEqual(expected);
      expect(availableAnimations.length).toBe(7);
    });
  });

  describe('comprehensive function mappings', () => {
    it('should handle all browser function variations', () => {
      const { getAnimationForTool } = useAnimation();

      const browserFunctions = [
        'browser_navigate',
        'browser_click',
        'browser_type',
        'browser_get_content',
        'browser_agent_navigate',
        'browser_agent_extract',
      ];

      browserFunctions.forEach((func) => {
        expect(getAnimationForTool(undefined, func)).toBe('globe');
      });
    });

    it('should handle all search function variations', () => {
      const { getAnimationForTool } = useAnimation();

      const searchFunctions = ['search_web', 'search_google'];

      searchFunctions.forEach((func) => {
        expect(getAnimationForTool(undefined, func)).toBe('search');
      });
    });

    it('should handle all shell function variations', () => {
      const { getAnimationForTool } = useAnimation();

      expect(getAnimationForTool(undefined, 'shell_execute')).toBe('terminal');
    });

    it('should handle all code function variations', () => {
      const { getAnimationForTool } = useAnimation();

      expect(getAnimationForTool(undefined, 'code_execute')).toBe('code');
    });

    it('should handle all file function variations', () => {
      const { getAnimationForTool } = useAnimation();

      const fileFunctions = ['file_read', 'file_write'];

      fileFunctions.forEach((func) => {
        expect(getAnimationForTool(undefined, func)).toBe('file');
      });
    });
  });

  describe('reactive behavior', () => {
    it('should react to tool content updates', async () => {
      const { recommendedAnimation, isAnimationActive } = useAnimation(toolContent);

      // Initial state
      expect(recommendedAnimation.value).toBe('spinner');
      expect(isAnimationActive.value).toBe(false);

      // Add browser tool
      toolContent.value = {
        tool_call_id: 'test-1',
        name: 'browser',
        function: 'navigate',
        args: {},
        status: 'calling',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(recommendedAnimation.value).toBe('globe');
      expect(isAnimationActive.value).toBe(true);

      // Update to search
      toolContent.value = {
        tool_call_id: 'test-2',
        name: 'search',
        function: 'search_web',
        args: {},
        status: 'called',
        timestamp: Date.now(),
      };

      await nextTick();

      expect(recommendedAnimation.value).toBe('search');
      expect(isAnimationActive.value).toBe(false);

      // Clear content
      toolContent.value = undefined;

      await nextTick();

      expect(recommendedAnimation.value).toBe('spinner');
      expect(isAnimationActive.value).toBe(false);
    });
  });
});
