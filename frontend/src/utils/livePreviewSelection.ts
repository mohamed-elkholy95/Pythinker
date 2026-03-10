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
 *
 * In replay mode, always keep `'search'` so the structured SearchContentView
 * renders instead of a static browser screenshot (which would just show a
 * search engine page — not useful).
 */
export function shouldPreferBrowserPreviewForSearch(input: LivePreviewSelectionInput): boolean {
  if (input.baseViewType !== 'search') return false;
  if (input.enabled === false) return false;

  // Replay: show structured search results, not browser screenshots
  if (input.isReplayMode) return false;

  return Boolean(input.sessionId) && !input.isSessionComplete;
}

export function resolveLivePreviewViewType(input: LivePreviewSelectionInput): ContentViewType | null {
  return shouldPreferBrowserPreviewForSearch(input) ? 'live_preview' : input.baseViewType;
}
