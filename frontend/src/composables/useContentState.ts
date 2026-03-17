import { ref, computed, Ref, watch } from 'vue';
import type { ToolContent } from '../types/message';

/**
 * Content state type
 */
export type ContentStateType = 'loading' | 'error' | 'empty' | 'ready';

/**
 * Content state data interface
 */
export interface ContentStateData {
  type: ContentStateType;
  isLoading: boolean;
  hasError: boolean;
  isEmpty: boolean;
  isReady: boolean;
  content: unknown;
}

/**
 * Composable for managing content state in tool views
 *
 * Provides a unified way to handle the four primary states:
 * - loading: Content is being fetched/processed
 * - error: An error occurred
 * - empty: No content available
 * - ready: Content is available and ready to display
 *
 * @param toolContent - Optional reactive reference to current tool content
 * @returns Content state management utilities
 *
 * @example
 * ```ts
 * const { contentState, setLoading, setReady, setError, setEmpty } = useContentState(toolContent);
 *
 * // Check state
 * if (contentState.value.isLoading) { ... }
 *
 * // Update state
 * setLoading();
 * setReady(data);
 * setError('Failed to load');
 * setEmpty();
 * ```
 */
export function useContentState(toolContent?: Ref<ToolContent | undefined>) {
  const stateType = ref<ContentStateType>('loading');
  const content = ref<unknown>(null);

  /**
   * Computed state flags
   */
  const isLoading = computed(() => stateType.value === 'loading');
  const hasError = computed(() => stateType.value === 'error');
  const isEmpty = computed(() => stateType.value === 'empty');
  const isReady = computed(() => stateType.value === 'ready');

  /**
   * Combined content state object
   */
  const contentState = computed<ContentStateData>(() => ({
    type: stateType.value,
    isLoading: isLoading.value,
    hasError: hasError.value,
    isEmpty: isEmpty.value,
    isReady: isReady.value,
    content: content.value,
  }));

  /**
   * Detect if tool content has any data
   */
  const hasToolContent = computed(() => {
    if (!toolContent?.value) return false;
    const tc = toolContent.value.content;

    // Content doesn't exist
    if (!tc) return false;

    // Check for content based on type
    if (typeof tc === 'object' && tc !== null) {
      return Object.keys(tc).length > 0;
    }

    return false;
  });

  /**
   * Detect tool execution status
   */
  const toolStatus = computed(() => toolContent?.value?.status || null);

  /**
   * Set loading state
   */
  function setLoading() {
    stateType.value = 'loading';
    content.value = null;
  }

  /**
   * Set error state
   */
  function setError(errorMessage?: string) {
    stateType.value = 'error';
    content.value = errorMessage || null;
  }

  /**
   * Set empty state
   */
  function setEmpty() {
    stateType.value = 'empty';
    content.value = null;
  }

  /**
   * Set ready state with content
   */
  function setReady(newContent: unknown) {
    stateType.value = 'ready';
    content.value = newContent;
  }

  /**
   * Reset to initial loading state
   */
  function reset() {
    setLoading();
  }

  /**
   * Auto-update state based on tool content changes
   */
  if (toolContent) {
    watch(
      () => toolContent.value,
      (tc) => {
        if (!tc) {
          setEmpty();
          return;
        }

        const status = tc.status;

        // Handle loading states (ToolContent status is only "calling" | "called")
        if (status === 'calling') {
          if (!isLoading.value) {
            setLoading();
          }
          return;
        }

        // Handle completed state with error check
        if (status === 'called') {
          // Check if content contains an error
          const content = tc.content;
          if (content && typeof content === 'object' && 'error' in content) {
            const errorMsg = typeof content.error === 'string' ? content.error : 'Operation failed';
            setError(errorMsg);
            return;
          }

          // Normal completion
          if (hasToolContent.value) {
            setReady(tc.content);
          } else {
            setEmpty();
          }
          return;
        }

        // Default to empty for unknown states
        if (!isReady.value && !isLoading.value) {
          setEmpty();
        }
      },
      { immediate: true, deep: true }
    );
  }

  return {
    // State
    contentState,
    stateType,
    content,

    // Computed flags
    isLoading,
    hasError,
    isEmpty,
    isReady,

    // Tool-derived state
    hasToolContent,
    toolStatus,

    // Methods
    setLoading,
    setError,
    setEmpty,
    setReady,
    reset,
  };
}
