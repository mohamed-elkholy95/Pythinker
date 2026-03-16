import { computed, Ref } from 'vue';
import type { ToolContent } from '../types/message';
import type { AnimationType } from './useLoadingState';

/**
 * Tool name to animation mapping
 */
const TOOL_ANIMATIONS: Record<string, AnimationType> = {
  browser: 'globe',
  browser_agent: 'globe',
  search: 'search',
  shell: 'terminal',
  code_executor: 'code',
  file: 'file',
  file_read: 'file',
  file_write: 'file',
};

/**
 * Function name to animation mapping (overrides tool name)
 */
const FUNCTION_ANIMATIONS: Record<string, AnimationType> = {
  browser_navigate: 'globe',
  browser_click: 'globe',
  browser_type: 'globe',
  browser_get_content: 'globe',
  browser_agent_navigate: 'globe',
  browser_agent_extract: 'globe',
  search_web: 'search',
  search_google: 'search',
  shell_execute: 'terminal',
  code_execute: 'code',
  file_read: 'file',
  file_write: 'file',
};

/**
 * Composable for animation selection and control
 *
 * Automatically selects appropriate animations based on tool type,
 * function name, and operation context.
 *
 * @param toolContent - Reactive reference to current tool content
 * @returns Animation utilities and recommended animation type
 *
 * @example
 * ```ts
 * const { recommendedAnimation, getAnimationForTool } = useAnimation(toolContent);
 *
 * // Use recommended animation (auto-detected from toolContent)
 * <LoadingState :animation="recommendedAnimation" />
 *
 * // Get animation for specific tool
 * const anim = getAnimationForTool('browser', 'browser_navigate');
 * ```
 */
export function useAnimation(toolContent?: Ref<ToolContent | undefined>) {
  /**
   * Get animation type for a specific tool and function
   */
  function getAnimationForTool(
    toolName?: string,
    functionName?: string
  ): AnimationType {
    // Function-specific override takes precedence
    if (functionName && FUNCTION_ANIMATIONS[functionName]) {
      return FUNCTION_ANIMATIONS[functionName];
    }

    // Tool name mapping
    if (toolName && TOOL_ANIMATIONS[toolName]) {
      return TOOL_ANIMATIONS[toolName];
    }

    // Default fallback
    return 'spinner';
  }

  /**
   * Get animation for current tool content
   */
  const recommendedAnimation = computed<AnimationType>(() => {
    if (!toolContent?.value) return 'spinner';

    const toolName = toolContent.value.name;
    const functionName = toolContent.value.function;

    return getAnimationForTool(toolName, functionName);
  });

  /**
   * Check if animation should be active (pulsing/animating)
   */
  const isAnimationActive = computed(() => {
    if (!toolContent?.value) return false;
    const status = toolContent.value.status;
    return status === 'calling';
  });

  /**
   * Get success animation for completed operations
   */
  function getSuccessAnimation(): AnimationType {
    return 'check';
  }

  /**
   * Determine if tool operation is text-only (no visual animation needed)
   */
  const isTextOnlyOperation = computed(() => {
    if (!toolContent?.value) return false;
    const func = toolContent.value.function;

    const TEXT_ONLY_FUNCTIONS = new Set([
      'browser_get_content',
      'browser_agent_extract',
      'search_web',
      'file_read',
    ]);

    return func ? TEXT_ONLY_FUNCTIONS.has(func) : false;
  });

  /**
   * Get animation based on operation type
   */
  function getAnimationByType(
    type: 'network' | 'search' | 'file' | 'shell' | 'code' | 'generic'
  ): AnimationType {
    switch (type) {
      case 'network':
        return 'globe';
      case 'search':
        return 'search';
      case 'file':
        return 'file';
      case 'shell':
        return 'terminal';
      case 'code':
        return 'code';
      default:
        return 'spinner';
    }
  }

  /**
   * All available animation types
   */
  const availableAnimations: AnimationType[] = [
    'globe',
    'search',
    'file',
    'terminal',
    'code',
    'spinner',
    'check',
  ];

  return {
    // Computed
    recommendedAnimation,
    isAnimationActive,
    isTextOnlyOperation,

    // Methods
    getAnimationForTool,
    getAnimationByType,
    getSuccessAnimation,

    // Constants
    availableAnimations,
  };
}
