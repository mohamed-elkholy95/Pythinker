import { computed, Ref, ref, watch } from 'vue';
import type { ToolContent } from '../types/message';
import {
  TOOL_CONTENT_CONFIG,
  FUNCTION_VIEW_OVERRIDES,
  TEXT_ONLY_FUNCTIONS,
  ContentConfig,
  ViewMode,
  ContentViewType
} from '../constants/tool';

export interface ContentState {
  config: ContentConfig | null;
  viewMode: ViewMode;
  viewModeIndex: number;
  currentViewType: ContentViewType | null;
  isTextOnlyOperation: boolean;
  defaultViewMode: ViewMode;
}

export function useContentConfig(toolContent: Ref<ToolContent | undefined>) {
  // Current view mode index (0 = primary, 1 = secondary, 2 = tertiary)
  const viewModeIndex = ref(0);
  const hasNewOutput = ref(false);

  // Get content configuration for the current tool
  const contentConfig = computed<ContentConfig | null>(() => {
    const toolName = toolContent.value?.name;
    if (!toolName) return null;
    return TOOL_CONTENT_CONFIG[toolName] || null;
  });

  // Check if current function is text-only (no live preview needed)
  const isTextOnlyOperation = computed(() => {
    const func = toolContent.value?.function;
    return func ? TEXT_ONLY_FUNCTIONS.has(func) : false;
  });

  // Determine the default view mode based on function or tool config
  const defaultViewMode = computed<ViewMode>(() => {
    const func = toolContent.value?.function;

    // Check function-specific overrides first
    if (func && FUNCTION_VIEW_OVERRIDES[func]) {
      return FUNCTION_VIEW_OVERRIDES[func];
    }

    // Fall back to tool config default
    return contentConfig.value?.defaultView || 'primary';
  });

  // Convert ViewMode to index
  const viewModeToIndex = (mode: ViewMode): number => {
    switch (mode) {
      case 'primary': return 0;
      case 'secondary': return 1;
      case 'tertiary': return 2;
      default: return 0;
    }
  };

  // Convert index to ViewMode
  const indexToViewMode = (index: number): ViewMode => {
    switch (index) {
      case 0: return 'primary';
      case 1: return 'secondary';
      case 2: return 'tertiary';
      default: return 'primary';
    }
  };

  // Current view mode as enum
  const currentViewMode = computed<ViewMode>(() => indexToViewMode(viewModeIndex.value));

  // Get the current content view type based on view mode
  const currentViewType = computed<ContentViewType | null>(() => {
    if (!contentConfig.value) return null;

    switch (currentViewMode.value) {
      case 'primary':
        return contentConfig.value.primaryView;
      case 'secondary':
        return contentConfig.value.secondaryView || null;
      case 'tertiary':
        return contentConfig.value.tertiaryView || null;
      default:
        return contentConfig.value.primaryView;
    }
  });

  // Set view mode by index
  const setViewModeByIndex = (index: number) => {
    viewModeIndex.value = index;
    hasNewOutput.value = false;
  };

  // Set view mode by enum
  const setViewMode = (mode: ViewMode) => {
    viewModeIndex.value = viewModeToIndex(mode);
    hasNewOutput.value = false;
  };

  // Reset to default view mode
  const resetToDefault = () => {
    viewModeIndex.value = viewModeToIndex(defaultViewMode.value);
    hasNewOutput.value = false;
  };

  // Mark that there's new output (for notification dot)
  const markNewOutput = () => {
    // Only mark new output if not on secondary view
    if (viewModeIndex.value !== 1) {
      hasNewOutput.value = true;
    }
  };

  // Watch for tool changes and reset view mode
  watch(
    () => toolContent.value?.tool_call_id,
    () => {
      resetToDefault();
    },
    { immediate: true }
  );

  // Computed state object for convenience
  const state = computed<ContentState>(() => ({
    config: contentConfig.value,
    viewMode: currentViewMode.value,
    viewModeIndex: viewModeIndex.value,
    currentViewType: currentViewType.value,
    isTextOnlyOperation: isTextOnlyOperation.value,
    defaultViewMode: defaultViewMode.value
  }));

  return {
    // State
    contentConfig,
    viewModeIndex,
    currentViewMode,
    currentViewType,
    isTextOnlyOperation,
    defaultViewMode,
    hasNewOutput,
    state,

    // Actions
    setViewModeByIndex,
    setViewMode,
    resetToDefault,
    markNewOutput
  };
}
