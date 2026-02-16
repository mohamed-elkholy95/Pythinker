import { ref, computed, Ref } from 'vue';
import type { ToolContent } from '../types/message';

/**
 * Animation type for loading states
 */
export type AnimationType = 'globe' | 'search' | 'file' | 'terminal' | 'code' | 'spinner' | 'check';

/**
 * Loading state interface
 */
export interface LoadingState {
  label: string;
  detail?: string;
  animation: AnimationType;
  isActive: boolean;
}

/**
 * Composable for managing loading states in tool views
 *
 * @param toolContent - Reactive reference to current tool content
 * @returns Loading state management utilities
 *
 * @example
 * ```ts
 * const { loadingState, setLoading, clearLoading } = useLoadingState(toolContent);
 *
 * // Set loading state
 * setLoading('Fetching data', { detail: 'example.com', animation: 'globe' });
 *
 * // Clear loading
 * clearLoading();
 * ```
 */
export function useLoadingState(toolContent?: Ref<ToolContent | undefined>) {
  const label = ref<string>('Loading');
  const detail = ref<string | undefined>(undefined);
  const animation = ref<AnimationType>('spinner');
  const isActive = ref(true);
  const isLoading = ref(false);

  /**
   * Combined loading state object
   */
  const loadingState = computed<LoadingState>(() => ({
    label: label.value,
    detail: detail.value,
    animation: animation.value,
    isActive: isActive.value,
  }));

  /**
   * Detect if tool is currently executing
   */
  const isToolExecuting = computed(() => {
    if (!toolContent?.value) return false;
    const status = toolContent.value.status;
    return status === 'calling';
  });

  /**
   * Set loading state with optional configuration
   */
  function setLoading(
    newLabel: string,
    options?: {
      detail?: string;
      animation?: AnimationType;
      isActive?: boolean;
    }
  ) {
    isLoading.value = true;
    label.value = newLabel;
    detail.value = options?.detail;
    animation.value = options?.animation || 'spinner';
    isActive.value = options?.isActive !== undefined ? options.isActive : true;
  }

  /**
   * Clear loading state
   */
  function clearLoading() {
    isLoading.value = false;
    detail.value = undefined;
  }

  /**
   * Update only the loading detail
   */
  function updateDetail(newDetail: string | undefined) {
    detail.value = newDetail;
  }

  /**
   * Update only the animation type
   */
  function updateAnimation(newAnimation: AnimationType) {
    animation.value = newAnimation;
  }

  return {
    // State
    loadingState,
    isLoading,
    isToolExecuting,

    // Individual properties (for direct binding)
    label,
    detail,
    animation,
    isActive,

    // Methods
    setLoading,
    clearLoading,
    updateDetail,
    updateAnimation,
  };
}
