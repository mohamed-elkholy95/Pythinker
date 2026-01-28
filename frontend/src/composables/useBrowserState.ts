import { ref, computed } from 'vue';
import type { ToolContent } from '@/types/message';

// Global state for current browser activity
const currentBrowserUrl = ref<string>('');
const currentBrowserAction = ref<string>('');
const browserHistory = ref<Array<{ url: string; timestamp: number }>>([]);

export function useBrowserState() {
  /**
   * Update browser state from tool content
   */
  const updateBrowserState = (toolContent: ToolContent) => {
    if (!toolContent) return;

    const { function: func, args } = toolContent;

    // Update URL if it's a navigation action
    if (func === 'browser_navigate' && args?.url) {
      const url = args.url;
      currentBrowserUrl.value = url;

      // Add to history
      browserHistory.value.push({
        url,
        timestamp: Date.now(),
      });

      // Keep only last 50 entries
      if (browserHistory.value.length > 50) {
        browserHistory.value = browserHistory.value.slice(-50);
      }
    }

    // Update current action
    const actionMap: Record<string, string> = {
      browser_navigate: 'Browsing',
      browser_click: 'Clicking',
      browser_input: 'Typing',
      browser_get_content: 'Reading page',
      browser_view: 'Viewing',
      browser_console_exec: 'Executing JavaScript',
      browser_scroll_up: 'Scrolling',
      browser_scroll_down: 'Scrolling',
      browser_press_key: 'Pressing keys',
      browser_move_mouse: 'Moving cursor',
      browser_select_option: 'Selecting option',
      browser_restart: 'Restarting browser',
    };

    currentBrowserAction.value = actionMap[func] || '';
  };

  /**
   * Clear browser state
   */
  const clearBrowserState = () => {
    currentBrowserUrl.value = '';
    currentBrowserAction.value = '';
  };

  /**
   * Get the most recent URL
   */
  const latestUrl = computed(() => {
    if (browserHistory.value.length === 0) return '';
    return browserHistory.value[browserHistory.value.length - 1].url;
  });

  /**
   * Check if currently browsing
   */
  const isBrowsing = computed(() => {
    return currentBrowserUrl.value.length > 0;
  });

  return {
    currentBrowserUrl,
    currentBrowserAction,
    browserHistory,
    latestUrl,
    isBrowsing,
    updateBrowserState,
    clearBrowserState,
  };
}
