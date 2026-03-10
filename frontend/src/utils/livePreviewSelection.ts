import type { ContentViewType } from '@/constants/tool';

export interface LivePreviewSelectionInput {
  baseViewType: ContentViewType | null;
  sessionId?: string;
  enabled?: boolean;
  isReplayMode?: boolean;
  hasReplayScreenshot?: boolean;
  isSessionComplete?: boolean;
}

/**
 * Search tools often trigger visible browser navigation in the sandbox.
 * Prefer the browser preview when that visual state is available so users
 * can follow the agent's browsing in both the main panel and mini preview.
 */
export function shouldPreferBrowserPreviewForSearch(input: LivePreviewSelectionInput): boolean {
  if (input.baseViewType !== 'search') return false;
  if (input.enabled === false) return false;

  if (input.isReplayMode) {
    return Boolean(input.hasReplayScreenshot);
  }

  return Boolean(input.sessionId) && !input.isSessionComplete;
}

export function resolveLivePreviewViewType(input: LivePreviewSelectionInput): ContentViewType | null {
  return shouldPreferBrowserPreviewForSearch(input) ? 'live_preview' : input.baseViewType;
}
